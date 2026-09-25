"""Driver System V2 assembly pins (docs/efv-v2/DRIVER_SYSTEM_V2.md s4.3, s5): DS-07 (the
output map), DS-08 (the combiner rule and its row set), DS-09 (protection status on
outcome-blind ids, as of the read), DS-10 (the pitcher K rate under the admission rule,
pitchers at the consensus order otherwise), the BMI re-test and the PV-12 slot.

TRAINING paths only: nothing here scores V2 against consensus or an outcome on a scored
row, and nothing reads a reserved frame.
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

import efv_drivers as DRV  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

ASSEMBLY = ROOT / "data" / "efv_v2_assembly.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"
PROGRESS = ROOT / "data" / "efv_progress.json"
WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}


# ---------------------------------------------------------------------------
# synthetic rows
# ---------------------------------------------------------------------------

def _feats(block=True, **kw):
    f = {"milb_unavailable": 0.0 if block else 1.0, "milb_missing": 0.0,
         "obp_rel": 0.0, "k_rel": 0.0, "peak_k_rel": 0.0, "level_rank": 0.0,
         "age_rel_level": 0.0, "tool_hit": 50.0, "tool_speed": 48.0,
         "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _rows(side="hit", years=range(2011, 2020), n=150, seed=11, k_sign=None,
          frame="lv"):
    """Rows with a planted driver: hitters tool_hit, pitchers k_rel (its sign per year
    from k_sign, default +1 every year). Consensus explains part of the target."""
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        s = 1.0 if k_sign is None else float(k_sign.get(yr, 1.0))
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else s * 20.0 * kr
            t = 0.1 * (fv - 45) + drv + float(rng.normal(0, 1))
            feats = _feats(True, tool_hit=th, k_rel=kr, peak_k_rel=kr,
                           obp_rel=float(rng.normal(0, 0.03)),
                           level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2),
                     "nov_add": float(rng.random() < 0.1)}
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra,
                        "v2": H.v2_row(feats, extra), "frame": frame,
                        "ids_outcome_blind": frame == "lv"})
            i += 1
    return out


# ---------------------------------------------------------------------------
# candidate lists
# ---------------------------------------------------------------------------

def test_candidate_lists_pinned():
    assert H.skill_candidates("hit") == H.V2_SKILL_KEYS["hit"] + ("pl_rev",)
    assert H.skill_candidates("pit") == ("k_rel", "bmi", "pl_rev")
    for side in F.SIDES:
        assert H.V2_ABSENCE_KEY not in H.skill_candidates(side)
        assert not set(H.timing_candidates(side)) & set(H.V2_PROTECTION_KEYS)
        lv = H.timing_candidates(side, ids_outcome_blind=True)
        assert set(H.V2_PROTECTION_KEYS) <= set(lv)
    # BMI is a pitcher re-test only; protection never reaches a skill head
    assert "bmi" not in H.skill_candidates("hit")
    for side in F.SIDES:
        assert not set(H.skill_candidates(side)) & set(H.V2_PROTECTION_KEYS)


def test_absence_flag_still_refused_in_the_skill_head():
    rows = _rows()
    with pytest.raises(ValueError):
        H.fit_skill_head(rows, "hit", candidates=("tool_hit", H.V2_ABSENCE_KEY))
    with pytest.raises(ValueError):
        H.fit_timing_head(rows, "hit", candidates=("level_rank", H.V2_ABSENCE_KEY))


def test_sidecar_keys_impute_at_the_observed_train_mean():
    a = H.v2_row(_feats(), {"bmi": 24.0})
    b = H.v2_row(_feats(), {"bmi": 26.0})
    c = H.v2_row(_feats(), {"bmi": None})
    assert c["bmi"] is None and c["pl_rev"] is None and c["on_40man"] is None
    means = H.has_block_means([{"v2": a}, {"v2": b}, {"v2": c}])
    assert means["bmi"] == pytest.approx(25.0)
    assert H.v2_vector(c, ("bmi",), means) == [25.0]
    assert H.v2_row(_feats(), {"bmi": True})["bmi"] is None       # a flag is not a value


# ---------------------------------------------------------------------------
# DS-07: the output map
# ---------------------------------------------------------------------------

def test_output_map_reorders_inside_groups_onto_consensus_values():
    rng = np.random.default_rng(5)
    groups = [2017] * 40 + [2018] * 60
    cons = np.round(rng.normal(45, 5, 100) * 2) / 2
    order = rng.normal(size=100)
    g = H.output_map(order, groups, cons)
    for yr in (2017, 2018):
        ix = [i for i, x in enumerate(groups) if x == yr]
        # the group's grade multiset IS its consensus multiset (no order ties here)
        assert sorted(g[ix]) == pytest.approx(sorted(cons[ix]))
        # and the grade orders the group exactly as order_idx does
        o, v = order[ix], g[ix]
        for a in range(len(ix)):
            for b in range(len(ix)):
                if o[a] < o[b]:
                    assert v[a] <= v[b]


def test_output_map_averages_order_ties_and_keeps_groups_apart():
    g = H.output_map([1.0, 1.0, 2.0, 0.0], ["a", "a", "a", "b"], [40.0, 50.0, 60.0, 99.0])
    assert g.tolist() == [45.0, 45.0, 60.0, 99.0]


def test_war_map_is_a_line_in_the_grade():
    rows = _rows(n=60, years=range(2012, 2014))
    m = H.fit_war_map(rows)
    grid = np.linspace(30, 70, 9)
    w = H.war_at(m, grid)
    assert np.allclose(np.diff(w), np.diff(w)[0])                  # linear, no table
    assert set(m) == {"a", "b", "n"}


# ---------------------------------------------------------------------------
# DS-08: the combiner rule
# ---------------------------------------------------------------------------

def test_combiner_rule_reads_no_row_after_its_last_year():
    rows = _rows(years=range(2011, 2020))
    base = H.combiner_rule("hit", {"lv": rows}, absent_ok=False)
    poisoned = [dict(r, target=1e6 * (i % 7), reached=float(i % 2),
                     v2=dict(r["v2"], tool_hit=-999.0))
                if r["decision_year"] > H.RULE_LAST_YEAR else r
                for i, r in enumerate(rows)]
    again = H.combiner_rule("hit", {"lv": poisoned}, absent_ok=False)
    assert again["coef"] == base["coef"]
    assert again["w_skill"] == base["w_skill"] and again["w_time"] == base["w_time"]
    assert max(base["sources"]["lv"]["years"]) <= H.RULE_LAST_YEAR
    assert all(int(y) <= H.RULE_LAST_YEAR for y in base["sources"]["lv"]["folds"])


def test_combiner_rule_finds_a_planted_skill_weight_and_bounds_it():
    r = H.combiner_rule("hit", {"lv": _rows(n=300)}, absent_ok=False)
    assert r["status"] == "ok"
    assert 0.0 < r["w_skill"] <= H.W_MAX
    assert r["w_skill_ratio"] is not None and r["coef"]["e_skill"] > 0
    assert H._share(3.0) == H.W_MAX and H._share(-0.2) == 0.0 and H._share(None) == 0.0


def test_combiner_rule_not_estimable_without_rows():
    r = H.combiner_rule("hit", {"lv": _rows(years=range(2017, 2020))}, absent_ok=False)
    assert r["status"] == "not_estimable" and r["w_skill"] == 0.0 and r["w_time"] == 0.0


def test_scored_years_start_after_the_rule():
    assert H.V2_FIRST_SCORED_YEAR == H.RULE_LAST_YEAR + 1
    for y in (2014, H.RULE_LAST_YEAR):
        with pytest.raises(ValueError):
            H._check_scored_year(y)
    H._check_scored_year(H.V2_FIRST_SCORED_YEAR)
    with pytest.raises(ValueError):
        H.v2_vm_scores("hit", weights=WEIGHTS, years=[2016], data=_rows(frame="vm"))
    with pytest.raises(F.ReservedFrameError):
        H.v2_vm_scores("hit", weights=WEIGHTS, years=[2025], data=_rows(frame="vm"))


@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_list_vintages_raise(V):
    with pytest.raises(F.ReservedFrameError):
        H.v2_lv_scores("hit", V, [], [], weights=WEIGHTS)
    with pytest.raises(F.ReservedFrameError):
        H.lv_v2_rows("hit", V, [])


# ---------------------------------------------------------------------------
# the assembled fit
# ---------------------------------------------------------------------------

def test_pitchers_take_the_consensus_order_without_an_admitted_skill_driver():
    # the K-rate sign flips in one training vintage, so the rule refuses it and the BMI
    # column is noise: no pitcher skill driver is admitted
    flip = {2014: -1.0}
    tr = _rows("pit", years=range(2011, 2017), k_sign=flip)
    te = _rows("pit", years=[2017], seed=99)
    m = H.fit_v2(tr, "pit", frame="lv", weights=WEIGHTS, absent_ok=False)
    assert m["consensus_only"] and "DS-Q2" in m["consensus_only_reason"]
    assert m["timing"] is None
    out = H.predict_v2(m, te)
    assert [o["order_idx"] for o in out] == [o["u_c"] for o in out]
    fv = [r["fv"] for r in te]
    order = np.argsort([o["efv_grade"] for o in out], kind="mergesort")
    assert np.all(np.diff(np.asarray(fv)[order]) >= 0)


def test_pitchers_move_when_the_k_rate_is_admitted():
    tr = _rows("pit", years=range(2011, 2017))
    te = _rows("pit", years=[2017], seed=99)
    m = H.fit_v2(tr, "pit", frame="lv", weights=WEIGHTS, absent_ok=False)
    assert "k_rel" in m["skill"]["keys"] and not m["consensus_only"]
    assert m["skill"]["admission"]["k_rel"]["admitted"]
    out = H.predict_v2(m, te)
    assert any(o["order_idx"] != o["u_c"] for o in out)
    # the grade stays on the group's consensus values
    assert sorted(o["efv_grade"] for o in out) == pytest.approx(sorted(r["fv"] for r in te))


def test_protection_never_enters_a_matrix_fit():
    tr = _rows(years=range(2011, 2017), frame="vm")
    m = H.fit_v2(tr, "hit", frame="vm", weights=WEIGHTS)
    t = m["timing"]
    assert t is None or not set(t["candidates"]) & set(H.V2_PROTECTION_KEYS)
    assert H.V2_ABSENCE_KEY not in (t or {}).get("candidates", [])


def test_zero_weights_reproduce_consensus_exactly():
    tr = _rows(years=range(2011, 2017))
    te = _rows(years=[2017], seed=3)
    zero = {"hit": {"w_skill": 0.0, "w_time": 0.0}, "pit": {"w_skill": 0.0, "w_time": 0.0}}
    m = H.fit_v2(tr, "hit", frame="lv", weights=zero, absent_ok=False)
    assert m["consensus_only"]
    out = H.predict_v2(m, te)
    assert [o["efv_grade"] for o in out] == pytest.approx(
        list(H.output_map([r["fv"] for r in te], [2017] * len(te), [r["fv"] for r in te])))


def test_lv_training_rows_drop_unresolved_labels_and_check_alignment():
    def frame_row(k, c):
        return {"player_key": k, "vintage": 2016, "grades": {"prospx_consensus": c},
                "prior": {}, "milb": None, "window": ["2016-01-01", "2016-05-01"],
                "mlbam_id": None}
    rows = [frame_row("a", 45.0), frame_row("b", 50.0), frame_row("c", None)]
    labs = [{"player_key": "a", "w3": 1.2, "r3": 1.0},
            {"player_key": "b", "w3": None, "r3": None},          # e.g. reserved_vm
            {"player_key": "c", "w3": 0.0, "r3": 0.0}]
    out = H.lv_training_rows("hit", {2016: (rows, labs)})
    assert [r["player_key"] for r in out] == ["a"]
    assert out[0]["target"] == 1.2 and out[0]["reached"] == 1.0
    with pytest.raises(ValueError):
        H.lv_training_rows("hit", {2016: (rows, list(reversed(labs)))})


# ---------------------------------------------------------------------------
# DS-09, BMI, PV-12 inputs (efv_drivers)
# ---------------------------------------------------------------------------

def _tx():
    return {7: [("2014-06-01", "SGN", "club signed rhp x."),
                ("2015-11-20", "SE", "club selected the contract of rhp x."),
                ("2016-01-01", "OUT", "club outrighted rhp x."),
                ("2016-03-01", "DES", "club designated rhp x.")],
            8: [("2013-08-01", "SGN", "club signed of y to a major league contract."),
                ("2015-12-02", "OPT", "club optioned of y.")]}


def test_protection_is_read_strictly_before_the_window():
    idx = _tx()
    p = DRV.protection_asof(7, 2016, idx)
    assert p["on_40man"] == 1.0 and p["nov_add"] == 1.0      # the 2016-01-01 outright is not known
    p17 = DRV.protection_asof(7, 2017, idx)
    assert p17["on_40man"] == 0.0 and p17["nov_add"] == 0.0
    assert DRV.protection_asof(8, 2014, idx)["on_40man"] == 1.0   # major league contract
    assert DRV.protection_asof(None, 2016, idx)["on_40man"] is None
    # a resolved id with no line in a complete feed was never protected
    p9 = DRV.protection_asof(9, 2016, idx)
    assert p9["observed"] is True and p9["on_40man"] == 0.0 and p9["nov_add"] == 0.0
    # a vintage whose V - 1 precedes the complete feed is unobserved, not False
    assert DRV.protection_asof(7, DRV.LEAGUE_TX_FULL_FROM, idx)["on_40man"] is None


def test_protection_reads_the_outcome_blind_id_only():
    rows = [{"player_key": "x", "vintage": 2016, "mlbam_id": None, "record_mlbam_id": 7},
            {"player_key": "y", "vintage": 2016, "mlbam_id": 7, "record_mlbam_id": None}]
    DRV.protection_for_frame(rows, index=_tx())
    assert rows[0]["on_40man_at_v"] is None and rows[0]["protection_observed"] is False
    assert rows[1]["on_40man_at_v"] == 1.0 and rows[1]["nov_add_v_minus_1"] == 1.0


def test_bmi_never_reads_a_later_listing():
    panel = {"p": [{"vintage": "2017-02-15", "h": 74, "w": 200},
                   {"vintage": "2018-02-15", "h": 74, "w": 230}]}
    early = DRV.bmi_asof("p", "2017-03-01", panel)
    assert early == pytest.approx(703.0 * 200 / 74 ** 2, abs=1e-4)
    assert DRV.bmi_asof("p", "2016-12-31", panel) is None
    assert DRV.bmi_asof("p", "2018-02-15", panel) == pytest.approx(703.0 * 230 / 74 ** 2,
                                                                   abs=1e-4)


def test_pl_rev_only_on_pipeline_anchored_rows_and_before_the_read():
    rows = [{"player_key": "a", "mlbam_id": 1, "asof_date": "2023-03-01",
             "grades": {"mlb_pipeline": 45}},
            {"player_key": "b", "mlbam_id": 2, "asof_date": "2023-03-01",
             "grades": {"fangraphs": 45}},
            {"player_key": "c", "mlbam_id": 3, "asof_date": "2022-03-01",
             "grades": {"mlb_pipeline": 40}}]
    preds = {1: [("2022-10-15", 47.0)], 2: [("2022-10-15", 47.0)],
             3: [("2022-10-15", 47.0)]}
    DRV.pl_revision_for_rows(rows, preds)
    assert [r["pl_rev_at_read"] for r in rows] == [47.0, None, None]
    assert DRV.PL_REV_FIRST_LIST_VINTAGE > max(F.RESERVED_LV)
    assert DRV.pl_revision_for_rows([dict(rows[0])])[0]["pl_rev_at_read"] is None


# ---------------------------------------------------------------------------
# the committed registration artifact
# ---------------------------------------------------------------------------

def _doc():
    if not ASSEMBLY.exists():
        pytest.skip("data/efv_v2_assembly.json not built")
    return json.loads(ASSEMBLY.read_text(encoding="utf-8"))


def test_registration_contract():
    doc = _doc()
    assert doc["role"] == "development" and doc["adjudicates"] is False
    assert doc["registered_before_any_read"] is True
    assert doc["model_id"] == H.V2_ASSEMBLED_ID
    g = doc["guards"]
    assert not set(g["lv_vintages_read"]) & set(F.RESERVED_LV)
    assert set(g["lv_vintages_read"]) <= set(F.DEV_VINTAGES)
    assert g["rule_last_year"] < min(g["scored_folds"])
    for side in F.SIDES:
        w = doc["weights"][side]
        assert 0.0 <= w["w_skill"] <= H.W_MAX and 0.0 <= w["w_time"] <= H.W_MAX
        rule = doc["rule"][side]
        assert (w["w_skill"], w["w_time"]) == (rule["w_skill"], rule["w_time"])
        for src in rule["sources"].values():
            assert all(y <= H.RULE_LAST_YEAR for y in src["years"])
    assert H.load_weights(ASSEMBLY)["hit"]["w_skill"] == doc["weights"]["hit"]["w_skill"]


def test_registration_arms_recompute_and_stay_in_development_folds():
    doc = _doc()
    for tag, a in doc["arms"].items():
        again = H.admission_check({int(v): t for v, t in a["t_by_vintage"].items()})
        assert again["admitted"] is a["admitted"], tag
        assert a["verdict"] == ("ADMITTED" if a["admitted"] else "REFUSED")
        assert all(int(v) in F.DEV_VINTAGES for v in a["per_vintage_signs"]), tag
        assert set(a["by_fold"]) == {str(v) for v in doc["guards"]["scored_folds"]}
    want = {f"V2-LV:{s}.skill.{k}" for s in F.SIDES for k in H.skill_candidates(s)}
    assert want <= set(doc["arms"])
    for s in F.SIDES:
        for k in H.V2_PROTECTION_KEYS:
            assert f"V2-LV:{s}.timing.{k}" in doc["arms"]
    # PV-12 has no row on any development vintage
    for s in F.SIDES:
        assert not doc["arms"][f"V2-LV:{s}.skill.pl_rev"]["admitted"]


def test_v2_reaches_the_progress_ledger_only_as_ds16_development_rows():
    # The assembly itself scores nothing; the first V2 rows are DS-16's development
    # read (tools/efv_v2_dev_read.py --ds16), and they adjudicate nothing.
    if not PROGRESS.exists():
        pytest.skip("progress ledger absent")
    doc = json.loads(PROGRESS.read_text(encoding="utf-8"))
    rows = [r for r in doc["rows"] if r.get("model_id") == H.V2_ASSEMBLED_ID]
    for r in rows:
        assert r["role"] == "development" and r["resolvable"] is None, r["run_id"]
        assert r["frame"] in ("vm_dev", "lv_dev")
        assert "within" in (r.get("statistic") or "")
        assert all(s["path"].endswith("efv_v2_dev_eval.json") for s in r["sources"])
        assert (r.get("verdict") or "").startswith("development only")


def test_ledger_counts_the_assembly():
    doc = _doc()
    if not LEDGER.exists():
        pytest.skip("ledger absent")
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [r for r in led["arms"] if r["artifact"] == "efv_v2_assembly.json"]
    assert len(rows) == len(doc["arms"])
    assert sum(1 for p in led["probes"] if p["artifact"] == "efv_v2_assembly.json") \
        == len(doc["probes"])


# ---------------------------------------------------------------------------
# gate compliance
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv", "fv_band",
           "fv_bin")


@pytest.mark.parametrize("mod", ["tools/efv_v2_assemble.py",
                                 "tools/backfill_mlb_transactions.py"])
def test_new_tools_group_nothing_by_grade(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED), (mod, name)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (mod, node.value, node.lineno)


def test_weights_are_finite_numbers():
    doc = _doc()
    for side in F.SIDES:
        for k in ("w_skill", "w_time"):
            assert math.isfinite(doc["weights"][side][k])
