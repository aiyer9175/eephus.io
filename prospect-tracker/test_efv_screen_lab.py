# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Screening lab pins (tools/efv_screen_lab.py; EFV3 lane B s4, EFV_V2_GATE.md s10).

1. Floors are derived and written before any arm.
2. A noise column never reads PASS (20 seeds); the twin of an admitted column reads
   a null; a column the rule refuses in a fold reproduces the base there (delta 0).
3. The verdict vocabulary is the standard's eight strings; an absence never reads as
   PASS; the exploratory run forms no verdict and may not write under data/.
4. The lab imports no served exporter, groups nothing by consensus-FV level, and the
   reserved guard trips on 2020.
5. The progress ledger copies a screening arm's numbers; the arm ledger reads the arm
   with the floor it was measured against.

Synthetic rows throughout; nothing here builds a real frame.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_progress as P  # noqa: E402
import efv_screen_lab as LAB  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

LAB_SRC = ROOT / "tools" / "efv_screen_lab.py"
WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}
B_FAST = 60          # more than the 49 usable draws a paired interval needs
N_PERM_FAST = 4
YEARS = range(2013, 2020)


# ---------------------------------------------------------------------------
# synthetic rows (the test_efv_v2_assembly pattern, plus a planted column)
# ---------------------------------------------------------------------------

def _feats(block=True, **kw):
    f = {"milb_unavailable": 0.0 if block else 1.0, "milb_missing": 0.0,
         "obp_rel": 0.0, "k_rel": 0.0, "peak_k_rel": 0.0, "level_rank": 0.0,
         "age_rel_level": 0.0, "tool_hit": 50.0, "tool_speed": 48.0,
         "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _rows(side="hit", years=YEARS, n=90, seed=11, plant=0.6):
    """Rows with a planted driver (hitters tool_hit, pitchers k_rel) and a planted
    extra column `x` whose weight is `plant`."""
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            x = float(rng.normal())
            t = 0.1 * (fv - 45) + drv + plant * x + float(rng.normal(0, 1))
            feats = _feats(True, tool_hit=th, k_rel=kr, peak_k_rel=kr,
                           obp_rel=float(rng.normal(0, 0.03)),
                           level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2),
                     "nov_add": float(rng.random() < 0.1)}
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                        "frame": "lv", "ids_outcome_blind": True, "x": x})
            i += 1
    return out


def _cand(name="planted_skill_hit", side="hit", head="skill"):
    return {"name": name, "side": side, "head": head, "kind": "column", "retest": False,
            "column": {"source": "values"}, "what": "synthetic"}


@pytest.fixture(scope="module")
def frame():
    hit, pit = _rows("hit"), _rows("pit", seed=12)
    fr = LAB.Frame.from_rows({"hit": hit, "pit": pit}, weights=WEIGHTS, w_star=1.5,
                             absent_ok={"hit": False, "pit": False})
    fr.planted = {(r["decision_year"], r["player_key"]): r["x"] for r in hit + pit}
    return fr


@pytest.fixture(scope="module")
def floors(frame):
    return LAB.derive_floors(frame, B=B_FAST, sides=("hit",), heads=("skill",),
                             mode="forced")


def _arm(frame, floors, values, name="planted_skill_hit", n_perm=N_PERM_FAST):
    a = LAB.measure_arm(frame, _cand(name), values, floors, B=B_FAST, n_perm=n_perm)
    a.pop("_order", None)
    return a


# ---------------------------------------------------------------------------
# 1. floors before arms
# ---------------------------------------------------------------------------

def test_floors_are_written_before_arms(frame, tmp_path):
    doc = LAB.run(frame, candidates=(_cand(),), frames=None, B=B_FAST, n_perm=N_PERM_FAST,
                  exploratory=False, both_floor_modes=False, log=lambda *_a: None,
                  extra_meta=None)
    # the synthetic candidate has no builder on this tree: unavailable, no verdict
    assert doc["arms"][0]["measured"] is False and doc["arms"][0]["verdict"] is None
    assert doc["floors_derived_before_arms"] is True
    out = tmp_path / "screen.json"
    LAB.write_doc(doc, out)
    text = out.read_text(encoding="utf-8")
    assert text.index('"floors"') < text.index('"arms"')
    keys = list(json.loads(text))
    assert keys.index("registration_echo") < keys.index("floors") < keys.index("arms")
    assert keys.index("label") < keys.index("floors") and keys.index("guards") < keys.index("floors")
    assert doc["holm"]["m"] == 1 and doc["holm"]["formed_after_every_arm"] is True


def test_floor_mode_admitted_reads_none_when_no_noise_is_admitted(frame):
    fl = LAB.derive_floors(frame, B=B_FAST, sides=("hit",), heads=("skill",),
                           mode="admitted", n_noise=1)
    blk = fl["skill"]["hit"]
    if blk["status"].startswith("degenerate"):
        assert blk["within"] is None and blk["auc"] is None
        assert all(r["within"]["mde95"] == 0.0 for r in blk["noise"])
    else:
        assert blk["within"] is not None and blk["within"] > 0
    assert fl["mode"] == "admitted"
    with pytest.raises(ValueError):
        LAB.derive_floors(frame, B=B_FAST, mode="whatever")


# ---------------------------------------------------------------------------
# 2. noise, twin, refusal
# ---------------------------------------------------------------------------

def test_a_noise_column_never_reads_pass_over_twenty_seeds(frame, floors):
    arms = []
    for seed in range(20):
        vals = LAB.noise_values(frame, "hit", 777 + seed)
        arms.append(_arm(frame, floors, vals, name=f"noise{seed}", n_perm=2))
    LAB.apply_verdicts(arms, m=len(arms), exploratory=False)
    for a in arms:
        assert a["verdict"] in LAB.VERDICTS
        assert a["verdict"] != "PASS", (a["name"], a["within"], a["clauses"])
        # an admitted noise column that happens to clear (a) still needs the family
        assert not (a["clauses"]["a_lb95_above_0_and_point_at_floor"]
                    and a["clauses"]["b_holm_p_below_alpha"])


def test_the_twin_of_an_admitted_column_reads_null(frame, floors):
    arm = _arm(frame, floors, frame.planted)
    assert arm["admitted_folds"] == arm["n_folds"] == len(frame.folds)
    assert arm["within"]["delta"] > 0 and arm["within"]["lb95"] > 0
    assert arm["fold_signs_agree"]
    twin_vals = LAB.permuted_values(frame.planted, arm["twin"]["seed"])
    assert sorted(twin_vals.values()) == pytest.approx(sorted(frame.planted.values()))
    twin = _arm(frame, floors, twin_vals, name="twin")
    LAB.apply_verdicts([arm, twin], m=2, exploratory=False)
    assert twin["verdict"] in ("NULL", "NULL_AUC_ONLY")
    assert arm["twin"]["inside_floor"] is True
    assert arm["clauses"]["c_twin_inside_floor"] is True
    assert arm["verdict"] in LAB.VERDICTS


def test_a_refused_column_reproduces_the_base_in_that_fold(frame):
    const = {slot: 1.0 for slot in frame.slots("hit")}
    frame.attach("hit", LAB.CANDIDATE_KEY, const)
    try:
        r = LAB.run_column(frame, "hit", "skill", LAB.CANDIDATE_KEY)
    finally:
        frame.detach("hit", LAB.CANDIDATE_KEY)
    for V, rec in r["folds"].items():
        assert rec["offered"] and rec["admitted"] is False
        base = frame.base("hit", int(V))["order"]
        for pk, idx in base.items():
            assert r["order"][(int(V), pk)] == idx
    cols = LAB._columns(frame, ("hit",), r["order"])
    assert LAB._within_point(cols) == 0.0
    for f in LAB._fold_deltas(cols).values():
        assert f["delta"] == 0.0 and f["sign"] == 0
    # and the column is gone from every row once detached
    assert not any(LAB.CANDIDATE_KEY in rw["v2"] for rw in frame.rows_of("hit"))


def test_a_forced_noise_column_is_refit_and_a_candidate_never_is_forced(frame):
    vals = LAB.noise_values(frame, "hit", 5)
    m = LAB.measure(frame, "hit", "skill", LAB.CANDIDATE_KEY, vals, B=B_FAST, force=True)
    assert all(f["admitted"] and f["forced"] for f in m["folds"].values())
    assert all("scr_cand" in f["head_keys"] for f in m["folds"].values())
    m2 = LAB.measure(frame, "hit", "skill", LAB.CANDIDATE_KEY, vals, B=B_FAST)
    assert all(f["forced"] is False for f in m2["folds"].values())


# ---------------------------------------------------------------------------
# 3. verdicts
# ---------------------------------------------------------------------------

def test_the_vocabulary_is_the_standards_eight_strings():
    assert LAB.VERDICTS == frozenset({
        "PASS", "VETO_ON_AUC", "NULL", "NULL_AUC_ONLY", "NULL_HOLM",
        "NOT_ADJUDICATED_NO_RHO_FLOOR", "NOT_ADJUDICATED_NO_AUC_FLOOR",
        "NOT_ADJUDICATED_NO_HOLM"})
    assert LAB.EXPLORATORY_VERDICT not in LAB.VERDICTS


def _fake_arm(*, delta=0.02, lb=0.01, floor=0.005, auc=0.0, auc_floor=0.01, twin=True,
              admitted=3, agree=True, balance=None, pooled=0.0, pooled_floor=0.01):
    return {"kind": "column", "within": {"delta": delta, "lb95": lb},
            "legs": {"within": LAB._leg(delta, floor), "auc": LAB._leg(auc, auc_floor),
                     "pooled": LAB._leg(pooled, pooled_floor)},
            "twin": {"inside_floor": twin}, "admitted_folds": admitted, "n_folds": 3,
            "fold_signs_agree": agree, "balance": balance}


@pytest.mark.parametrize("arm,holm,expect", [
    (_fake_arm(), {"survives_holm": True}, "PASS"),
    (_fake_arm(), {"survives_holm": False}, "NULL_HOLM"),
    (_fake_arm(), None, "NOT_ADJUDICATED_NO_HOLM"),
    (_fake_arm(auc_floor=None), {"survives_holm": True}, "NOT_ADJUDICATED_NO_AUC_FLOOR"),
    (_fake_arm(floor=None), {"survives_holm": True}, "NOT_ADJUDICATED_NO_RHO_FLOOR"),
    (_fake_arm(lb=-0.001), {"survives_holm": True}, "NULL"),
    (_fake_arm(lb=-0.001, auc=0.02), {"survives_holm": True}, "NULL_AUC_ONLY"),
    (_fake_arm(auc=-0.02), {"survives_holm": True}, "VETO_ON_AUC"),
    (_fake_arm(twin=False), {"survives_holm": True}, "NULL"),
    (_fake_arm(admitted=2), {"survives_holm": True}, "NULL"),
    (_fake_arm(agree=False), {"survives_holm": True}, "NULL"),
    (_fake_arm(balance={"hit": {"verdict": "IMBALANCED"}}), {"survives_holm": True}, "NULL"),
    (_fake_arm(pooled=-0.02), {"survives_holm": True}, "NULL"),
    (_fake_arm(delta=0.004), {"survives_holm": True}, "NULL"),
])
def test_screen_verdict_corners(arm, holm, expect):
    v = LAB.screen_verdict(arm, holm)
    assert v["verdict"] == expect and v["verdict"] in LAB.VERDICTS
    if expect.startswith("NOT_ADJUDICATED"):
        assert v["verdict"] != "PASS"


def test_exploratory_forms_no_verdict_and_never_writes_under_data(frame, floors):
    arm = _arm(frame, floors, frame.planted)
    LAB.apply_verdicts([arm], m=7, exploratory=True)
    assert arm["verdict"] == LAB.EXPLORATORY_VERDICT and arm["clauses"] is None
    assert arm["screening"]["exploratory"] is True
    assert any("exploratory" in s for s in arm["not_adjudicated"])
    # the CLI refuses an exploratory, reduced or partial run under data/ before it
    # builds anything
    assert LAB.main(["--exploratory"]) == 2
    assert LAB.main(["--B", "100"]) == 2
    assert LAB.main(["--n-perm", "10"]) == 2
    assert LAB.main(["--only", "txt_skill_hit"]) == 2
    assert LAB._is_under_data(LAB.OUT_DEFAULT)
    assert not LAB._is_under_data(ROOT / "x.json")


def test_holm_adjust_is_step_down_over_the_registered_m():
    out = LAB.holm_adjust({"a": 0.001, "b": 0.02, "c": 0.04, "d": None}, m=7)
    assert out["a"]["holm_p"] == pytest.approx(0.007) and out["a"]["survives_holm"]
    assert out["b"]["holm_p"] == pytest.approx(0.12) and not out["b"]["survives_holm"]
    assert out["c"]["holm_p"] == pytest.approx(0.2) and not out["c"]["survives_holm"]
    assert out["d"]["survives_holm"] is None and out["d"]["p"] is None


# ---------------------------------------------------------------------------
# 4. registration, imports, grouping, guard
# ---------------------------------------------------------------------------

def test_wave_one_is_frozen():
    names = [c["name"] for c in LAB.CANDIDATES]
    assert names == ["txt_skill_hit", "txt_skill_pit", "txt_time_hit", "txt_time_pit",
                     "milb_floor_2005", "pick_overall_time_hit", "pick_overall_time_pit"]
    assert LAB.registration_echo()["family_size"] == 7
    assert not any("seasons_at_level" in n for n in names)
    for c in LAB.CANDIDATES:
        if c["name"].startswith("pick_overall"):
            assert c["retest"] and c["head"] == "timing"
        if c["kind"] == "coverage":
            assert c["head"] is None and c["side"] == LAB.BOTH
        else:
            assert c["head"] in LAB.HEADS and c["side"] in F.SIDES
    assert LAB.FOLDS == (2017, 2018, 2019)
    assert LAB.B_DEFAULT == 2000 and LAB.SEED == 20260906 and LAB.N_PERM == 500
    assert LAB.N_NOISE == 3 and LAB.FLOOR_MODE_DEFAULT == "forced"
    echo = LAB.registration_echo()
    assert echo["holm"]["m"] == 7 and echo["estimator"]["seed"] == 20260906
    assert "vm_dev" in " ".join(echo["not_arms"])


_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def _imports(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name
        elif isinstance(n, ast.ImportFrom) and n.module:
            yield n.module


def test_the_lab_imports_no_served_exporter():
    tree = ast.parse(LAB_SRC.read_text(encoding="utf-8"))
    mods = {m.split(".")[0] for m in _imports(tree)}
    assert not mods & _SERVED_EXPORTERS, mods & _SERVED_EXPORTERS


_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name


def test_no_fv_or_consensus_grouping_in_the_lab():
    tree = ast.parse(LAB_SRC.read_text(encoding="utf-8"))
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), name
        assert not fv_group.search(low), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), node.value
    src = LAB_SRC.read_text(encoding="utf-8")
    assert "—" not in src and "–" not in src


def test_the_guard_trips_on_2020():
    with pytest.raises(F.ReservedFrameError):
        LAB.guards((2017, 2020))
    with pytest.raises(F.ReservedFrameError):
        LAB.guards((2020,))
    with pytest.raises(F.ReservedFrameError):
        LAB.Frame.from_rows({"hit": _rows("hit", years=range(2015, 2021), n=20)},
                            weights=WEIGHTS, folds=(2020,))
    g = LAB.guards()
    assert g["reserved_vm_pins"] == [] and g["lv_folds"] == [2017, 2018, 2019]
    assert g["vm_dev_screened"] is False and g["closed_arms_rerun"] is False


def test_fit_v2_default_path_carries_no_screening_key():
    rows = _rows("hit", n=40)
    assert H.screen_keys(rows) == ()
    m = H.fit_v2(rows, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    assert "extra" not in m
    with pytest.raises(ValueError):
        H.fit_v2(rows, "hit", frame="lv", weights=WEIGHTS, absent_ok=False,
                 extra={"skill": ("tool_hit",)})
    for r in rows:
        r["v2"]["scr_z"] = None
    rows[0]["v2"]["scr_z"] = 2.0
    rows[1]["v2"]["scr_z"] = 4.0
    assert H.screen_keys(rows) == ("scr_z",)
    assert H.has_block_means(rows)["scr_z"] == pytest.approx(3.0)
    assert H.v2_vector(rows[2]["v2"], ("scr_z",), H.has_block_means(rows)) == [3.0]
    with pytest.raises(ValueError):
        H.fit_skill_head(rows, "hit", candidates=("tool_hit",), force=("tool_hit",))


# ---------------------------------------------------------------------------
# 5. the ledgers copy the arm
# ---------------------------------------------------------------------------

def _artifact(frame, floors, exploratory=False):
    arm = _arm(frame, floors, frame.planted)
    LAB.apply_verdicts([arm], m=7, exploratory=exploratory)
    return {"generated_at": "2026-10-02T00:00:00Z", "role": "development",
            "exploratory": exploratory, "wave": 1,
            "label": {"provider": "ewar_v2", "resolved_through": 2025, "id": "ewar_v2@test"},
            "code": {"commit": "deadbeef"}, "floors": floors, "arms": [arm]}


def test_progress_rows_copy_a_screening_arm(frame, floors):
    doc = _artifact(frame, floors)
    docs = P.screen_arm_docs(doc)
    assert len(docs) == 1
    rows = P.build_dev_rows(docs[0], sources=[{"path": "data/xfv_screen_wave1.json"}],
                            date="2026-10-02", trigger="efv_change", now_iso="t",
                            frames=("lv_dev",), raters=P.SCREEN_RATERS,
                            deltas=P.SCREEN_DELTAS, statistic_fields=True)
    assert len(rows) == 1
    row = rows[0]
    arm = doc["arms"][0]
    assert row["model_id"] == arm["model_id"] == "efv_v2_screen:wave1:planted_skill_hit:hit"
    assert row["model_id"].startswith(P.SCREEN_MODEL_PREFIX)
    assert row["resolvable"] is None and row["role"] == "development"
    assert row["frame"] == "lv_dev" and "basis_key" not in row
    assert row["raters"]["efv"]["spearman"] == arm["frame"]["raters"]["efv_v2_candidate"]["within"]
    assert row["raters"]["efv_v2_base"]["spearman"] == arm["frame"]["raters"]["efv_v2_base"]["within"]
    leg = row["deltas"]["vs_efv_v2_base"]["spearman"]
    assert leg["delta"] == arm["within"]["delta"] and leg["mde95"] == arm["within"]["mde95"]
    assert row["verdict"] == arm["verdict"] and row["statistic"] == arm["frame"]["statistic"]
    assert row["screening"] == arm["screening"]
    assert row["screening"]["exploratory"] is False
    assert row["model_version"]["label"] == "ewar_v2@test"
    # the screening block is part of the content hash
    other = dict(row, screening=dict(row["screening"], head="timing"))
    assert P.content_hash(other) != P.content_hash(row)
    assert any(n == "xfv_screen_wave1.json" for n, *_ in P.DEV_ARTIFACTS)


def test_an_exploratory_arm_never_lands_a_progress_row(frame, floors):
    assert P.screen_arm_docs(_artifact(frame, floors, exploratory=True)) == []
    doc = _artifact(frame, floors)
    doc["arms"][0]["measured"] = False
    assert P.screen_arm_docs(doc) == []


def test_the_arm_ledger_reads_the_arm_with_its_own_floor(frame, floors, tmp_path, monkeypatch):
    import efv_arm_ledger as AL
    monkeypatch.setattr(AL, "DATA", tmp_path)
    led = AL.collect()
    assert any(p["artifact"] == "xfv_screen_wave1.json" for p in led["sources_pending"])
    assert not any(m["artifact"] == "xfv_screen_wave1.json" for m in led["sources_missing"])
    doc = _artifact(frame, floors)
    (tmp_path / "xfv_screen_wave1.json").write_text(json.dumps(doc), encoding="utf-8")
    led = AL.collect()
    mine = [r for r in led["arms"] if r["artifact"] == "xfv_screen_wave1.json"]
    assert len(mine) == 1
    r, arm = mine[0], doc["arms"][0]
    assert r["arm"] == arm["tag"] and r["verdict"] == arm["verdict"]
    assert r["delta_rho"] == arm["within"]["delta"] and r["floor_rho"] == arm["floor_rho"]
    assert r["cleared_own_floor"] is (arm["within"]["delta"] >= arm["floor_rho"])
    assert r["side"] == "hit"
    assert not any(p["artifact"] == "xfv_screen_wave1.json" for p in led["sources_pending"])
