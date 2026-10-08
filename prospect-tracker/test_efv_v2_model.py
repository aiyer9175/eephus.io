# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-09 pins for eFV v2 champion H0 (efv_v2_model.py, docs/efv-v2/PROGRAM.md s3.4).

1. Liveness: the offset-only model (both heads removed) orders rows EXACTLY as the
   consensus does, on synthetic data and on real folds of both sides.
2. No clip: a negative expected WAR stays negative; the only floors in the module are
   v1's, inside the v1 comparator.
3. Bit-exact: the same inputs reproduce every fit and score, and the bootstrap is
   reproducible by its seed (and moves with it).
4. One output: the board order, the comparison score and the pricing grade all derive
   from score_v2 and agree on the ordering.
5. The v1 comparator reproduces efv_model.oos_grades bit for bit.
6. The penalty CV is nested and forward-chained inside the training years.
7. Reserved frames raise; no FV-cell grouping in the module or the development read.
8. The committed development artifact keeps its contract.
"""
from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_model as V1
import efv_v2_model as H
import efv_vintage_frame as F
import source_backtest as SB

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))


def _synthetic(seed: int = 7, n_per_year: int = 80, years=range(2010, 2020),
               war_at_30: float = 1.0) -> list[dict]:
    """Rows shaped like efv_v2_model.training_rows: fv drives both REACHED and WAR.
    `war_at_30` is the expected WAR of a reached player at the bottom of the grade
    range; the default keeps it positive, as it is on the real folds."""
    rng = np.random.default_rng(seed)
    out = []
    for y in years:
        for i in range(n_per_year):
            fv = float(rng.choice(np.arange(30.0, 72.5, 2.5)))
            x1, x2 = float(rng.normal()), float(rng.normal())
            p = 1.0 / (1.0 + math.exp(-(-9.0 + 0.2 * fv + 0.6 * x1)))
            reached = 1.0 if rng.random() < p else 0.0
            war = war_at_30 + 0.3 * (fv - 30.0) + 1.5 * x2 + float(rng.normal()) * 2.0
            out.append({"player_key": f"p{y}_{i}", "kind": "debuted" if reached else "bust",
                        "decision_year": y, "fv": fv, "reached": reached,
                        "target": war if reached else 0.0, "weight": 1.0,
                        "feats": {"x1": x1, "x2": x2}})
    return out


def _same_order(scores, fvs) -> bool:
    """Sorting by score gives non-decreasing fv, and equal fv means equal score."""
    order = sorted(range(len(scores)), key=lambda i: (scores[i], fvs[i]))
    for a, b in zip(order, order[1:]):
        if fvs[b] < fvs[a]:
            return False
        if fvs[b] == fvs[a] and scores[b] != scores[a]:
            return False
    return True


# ---------------------------------------------------------------------------
# 1. liveness

def test_offset_only_reproduces_consensus_order_synthetic():
    rows = _synthetic()
    train = [r for r in rows if r["decision_year"] < 2019]
    test = [r for r in rows if r["decision_year"] == 2019]
    m = H.fit(train, "hit", keys=["x1", "x2"])
    assert m is not None
    off = H.predict(H.offset_only(m), test)
    assert _same_order([p["score"] for p in off], [r["fv"] for r in test])
    # the heads are live: with them on, the order is no longer the consensus order
    full = H.predict(m, test)
    assert not _same_order([p["score"] for p in full], [r["fv"] for r in test])


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_offset_only_reproduces_consensus_order_on_real_folds(side):
    data = H.training_rows(side)
    models = H.fold_models(side, years=(2019, 2022), data=data)
    assert set(models) == {2019, 2022}
    for yr, m in models.items():
        test = [r for r in data if r["decision_year"] == yr]
        fvs = [r["fv"] for r in test]
        off = H.predict(H.offset_only(m), test)
        assert _same_order([p["score"] for p in off], fvs), (side, yr)
        assert H.offset_curve_is_monotone(m, min(fvs), max(fvs))
    # offset-only oos scores equal the offset map applied directly
    oo = H.oos_scores(side, heads=False, years=(2019,), data=data, models=models)
    test = [r for r in data if r["decision_year"] == 2019]
    direct = H.predict(H.offset_only(models[2019]), test)
    assert [oo[r["player_key"]] for r in test] == [p["score"] for p in direct]


def test_monotone_domain_is_detected_not_assumed():
    """With no clip, P * E can turn at the bottom of the grade range when E there is
    strongly negative (d/dfv < 0 once E < -f_W' / ((1 - P) f_R')). The model does not
    hide it: offset_curve_is_monotone reports it, and the development read records it
    per fold. On the real folds E stays above that bound over the observed range
    (test above)."""
    rows = _synthetic(seed=11, war_at_30=-8.0)
    m = H.fit([r for r in rows if r["decision_year"] < 2019], "hit", keys=["x1", "x2"])
    assert H.offset_curve_is_monotone(m, 30.0, 70.0) is False
    lo = 30.0
    while lo < 70.0 and not H.offset_curve_is_monotone(m, lo, 70.0):
        lo += 0.5
    assert 30.0 < lo < 70.0      # monotone above a turning point inside the range


# ---------------------------------------------------------------------------
# 2. no clip

def test_no_clip_negative_expected_war_stays_negative():
    rows = _synthetic(seed=11, war_at_30=-8.0)
    train = [r for r in rows if r["decision_year"] < 2019]
    test = [r for r in rows if r["decision_year"] == 2019]
    m = H.fit(train, "hit", keys=["x1", "x2"])
    pr = H.predict(m, test)
    assert min(p["e_war_reached"] for p in pr) < -2.0      # below v1's model-leg floor
    assert min(p["score"] for p in pr) < 0.0                # below v1's consensus floor
    for p in pr:
        assert p["score"] == p["p_reached"] * p["e_war_reached"]


def test_no_floor_anywhere_but_the_v1_comparator():
    tree = ast.parse((ROOT / "efv_v2_model.py").read_text(encoding="utf-8"))
    v1_nodes = {id(n) for fn in ast.walk(tree)
                if isinstance(fn, ast.FunctionDef) and fn.name == "v1_fold_scorer"
                for n in ast.walk(fn)}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if id(fn) in v1_nodes:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("clip", "maximum", "minimum"), (fn.name, node.attr)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("max", "min")):
                consts = [a for a in node.args if isinstance(a, ast.Constant)]
                # the only constant-bounded max allowed is the 1e-3 weight guard, which
                # bounds a sample weight and never a prediction
                for c in consts:
                    assert c.value == 1e-3, (fn.name, node.lineno, c.value)


# ---------------------------------------------------------------------------
# 3. bit-exact and seeded

def test_fit_and_scores_are_bit_exact():
    data = H.training_rows("pit")
    a = H.fold_models("pit", years=(2020,), data=data)
    b = H.fold_models("pit", years=(2020,), data=H.training_rows("pit"))
    assert json.dumps(a[2020], sort_keys=True, default=str) == \
        json.dumps(b[2020], sort_keys=True, default=str)
    sa = H.oos_scores("pit", years=(2020,), data=data, models=a)
    sb = H.oos_scores("pit", years=(2020,), data=data, models=b)
    assert sa == sb and len(sa) >= H.MIN_TEST_ROWS


def test_bootstrap_is_seed_reproducible():
    import efv_v2_dev_read as R
    rng = np.random.default_rng(3)
    rows = []
    for i in range(300):
        w = float(rng.normal())
        rows.append({"key": f"k{i % 200}", "outcome": {"war": w, "contributor": w > 1.0},
                     "grades": {R.H0_KEY: w + float(rng.normal()),
                                R.V1_KEY: w + float(rng.normal()),
                                R.CONS: w + float(rng.normal()),
                                "mlb_pipeline": w + float(rng.normal()),
                                "fangraphs": w + float(rng.normal())}})
    d1 = R._deltas(rows, H.SEED, 200)
    d2 = R._deltas(rows, H.SEED, 200)
    d3 = R._deltas(rows, H.SEED + 1, 200)
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    assert json.dumps(d1, sort_keys=True) != json.dumps(d3, sort_keys=True)
    assert H.SEED == SB._CLAIM_SEED


# ---------------------------------------------------------------------------
# 4. one output drives board, comparison score and price

def test_one_output_drives_board_score_and_price():
    rng = np.random.default_rng(5)
    keys = [f"k{i}" for i in range(120)]
    scores = {k: float(rng.normal()) for k in keys}
    cons = {k: float(rng.choice(np.arange(35.0, 65.0, 5.0))) for k in keys}
    v = H.served_views(scores, cons)
    assert v["board_order"] == sorted(keys, key=lambda k: (-scores[k], k))
    assert v["comparison"] == scores
    order = v["board_order"]
    price = [v["price_grade"][k] for k in order]
    assert all(a >= b for a, b in zip(price, price[1:]))       # weakly monotone in score
    assert sorted(price) == sorted(cons.values())               # on the consensus scale


# ---------------------------------------------------------------------------
# 5. v1 comparator parity

@pytest.mark.parametrize("side", ["hit", "pit"])
def test_v1_fold_scorer_reproduces_oos_grades(side):
    g = V1.oos_grades(side)
    data = H.training_rows(side)
    seen = 0
    for yr in V1.SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
            continue
        sc = H.v1_fold_scorer(tr, side)
        for r, s in zip(te, sc(te)):
            assert g[r["player_key"]] == s
            seen += 1
    assert seen == len(g)


# ---------------------------------------------------------------------------
# 6. nested forward-chained penalty selection

def test_penalty_cv_is_nested_inside_training_years(monkeypatch):
    rows = _synthetic(seed=2)
    train = [r for r in rows if r["decision_year"] < 2019]
    inner = H.inner_years(train)
    assert inner and max(inner) < 2019
    seen = []
    real = H.fit_offsets

    def spy(tr):
        seen.append(max(r["decision_year"] for r in tr))
        return real(tr)
    monkeypatch.setattr(H, "fit_offsets", spy)
    sel = H.select_alphas(train, ["x1", "x2"])
    assert len(seen) == len(inner)
    for got, y in zip(seen, inner):
        assert got < y                     # the inner fit never sees its test year
    assert sel["alpha_r"] in H.ALPHAS and sel["alpha_w"] in H.ALPHAS
    assert math.isinf(H.ALPHAS[-1])        # heads off is always a candidate


def test_heads_off_when_no_inner_year():
    rows = [r for r in _synthetic(seed=4) if r["decision_year"] in (2010, 2011)]
    sel = H.select_alphas([r for r in rows if r["decision_year"] == 2010], ["x1", "x2"])
    assert math.isinf(sel["alpha_r"]) and math.isinf(sel["alpha_w"])


# ---------------------------------------------------------------------------
# 7. reserved frames and gate compliance

@pytest.mark.parametrize("years", [(2025,), (2024, 2025), (2026,)])
def test_reserved_vm_years_raise(years):
    with pytest.raises(F.ReservedFrameError):
        H.oos_scores("hit", years=years, data=[])
    with pytest.raises(F.ReservedFrameError):
        H.fold_models("hit", years=years, data=[])


@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_list_vintages_raise(V):
    with pytest.raises(F.ReservedFrameError):
        H.lv_scores("hit", V, [], data=[])


def test_scored_years_stay_clear_of_rvm():
    assert F.reserved_vm_pins() == []


_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


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


@pytest.mark.parametrize("mod", ["efv_v2_model.py", "tools/efv_v2_dev_read.py"])
def test_no_fv_cell_grouping(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for name in _names(tree):
        assert not any(t in name.lower() for t in _BANNED_TOKENS), (mod, name)
    # v1's fold gate (60 training rows) is the one grid-valued constant, and it
    # counts rows, not grades.
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MIN_TRAIN_ROWS" for t in node.targets):
            exempt.add(id(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) \
                and id(node) not in exempt:
            assert node.value not in _FV_GRID, (mod, node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), (mod, node.value)


# ---------------------------------------------------------------------------
# 8. the committed development artifact

def test_dev_artifact_contract():
    p = ROOT / "data" / "efv_v2_dev_eval.json"
    if not p.exists():
        pytest.skip("data/efv_v2_dev_eval.json not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["role"] == "development" and doc["adjudicates"] is False
    assert doc["model_id"] == H.MODEL_ID
    assert set(doc["frames"]) == {"vm_dev", "lv_dev"}
    g = doc["reserved_guard"]
    assert not set(g["lv_vintages_read"]) & set(F.RESERVED_LV)
    assert set(g["lv_vintages_read"]) <= set(F.DEV_VINTAGES)
    assert max(g["vm_years_read"]) < F.R_VM_FIRST_DEBUT_YEAR
    assert g["reserved_vm_pins"] == []
    vm = doc["frames"]["vm_dev"]
    assert vm["liveness"]["offset_only_reproduces_consensus_order"] is True
    assert vm["parity"]["reproduces"] is True
    for f in doc["frames"].values():
        for comp in f["deltas"].values():
            for leg in comp.values():
                assert leg["estimator"] == "E_cond"
    txt = json.dumps(doc, ensure_ascii=False)
    assert "—" not in txt and "–" not in txt


# ---------------------------------------------------------------------------
# 9. the screening flag (EFV3_B7, docs/efv-v2/EFV_V2_GATE.md s10.13): off by default,
#    the candidate lists and the fitted heads are the committed module's; on, an
#    admitted column reaches its declared head and nowhere else

import subprocess  # noqa: E402

_LIST_SKILL = {"hit": ("obp_rel", "contact", "tool_hit", "tool_speed", "is_college",
                       "level_rank", "pl_rev"),
               "pit": ("k_rel", "bmi", "pl_rev")}
_LIST_TIMING = {(False, False): ("age_rel_level", "level_rank"),
                (True, False): ("age_rel_level", "level_rank", "on_40man", "nov_add"),
                (True, True): ("age_rel_level", "level_rank", "milb_absent", "on_40man",
                               "nov_add")}
_W = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}


def _lv_rows(side: str, seed: int = 11, n: int = 90, plant: float = 0.6,
             key: str | None = None) -> list[dict]:
    """Labelled F-LV style rows with a planted driver (hitters tool_hit, pitchers
    k_rel) and, under `key`, a planted screening column on every row's v2 block."""
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in range(2013, 2020):
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            x = float(rng.normal())
            t = 0.1 * (fv - 45) + drv + plant * x + float(rng.normal(0, 1))
            feats = {"milb_unavailable": 0.0, "milb_missing": 0.0,
                     "obp_rel": float(rng.normal(0, 0.03)), "k_rel": kr, "peak_k_rel": kr,
                     "level_rank": float(rng.integers(0, 6)),
                     "age_rel_level": float(rng.normal(0, 1)), "tool_hit": th,
                     "tool_speed": 48.0, "is_college": 0.0, "is_ifa": 0.0,
                     "pick_missing": 1.0}
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2),
                     "nov_add": float(rng.random() < 0.1)}
            v2 = H.v2_row(feats, extra)
            if key:
                v2[key] = x
            out.append({"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": v2, "frame": "lv",
                        "ids_outcome_blind": True})
            i += 1
    return out


def _committed_module(tmp_path):
    """efv_v2_model.py as committed at HEAD, loaded under another name."""
    import importlib.util
    r = subprocess.run(["git", "show", "HEAD:./efv_v2_model.py"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not r.stdout:
        pytest.skip("the committed efv_v2_model.py is not readable here")
    p = tmp_path / "efv_v2_model_committed.py"
    p.write_text(r.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("efv_v2_model_committed", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dump(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def test_screen_flag_off_keeps_the_lists_the_heads_and_the_assembly(tmp_path):
    import efv_v2_serve as S
    assert H.V2_SCREEN_CANDIDATES_ON is False
    for side in F.SIDES:
        assert H.skill_candidates(side) == _LIST_SKILL[side]
        assert H.screen_admitted("skill", side) == () and H.screen_admitted("timing", side) == ()
        for (ob, ab), keys in _LIST_TIMING.items():
            assert H.timing_candidates(side, ids_outcome_blind=ob, absence_admitted=ab) == keys
    committed = _committed_module(tmp_path)
    for side in F.SIDES:
        assert committed.skill_candidates(side) == H.skill_candidates(side)
        rows = _lv_rows(side)
        a = H.fit_v2(rows, side, frame="lv", weights=_W, absent_ok=False)
        b = committed.fit_v2(rows, side, frame="lv", weights=_W, absent_ok=False)
        assert _dump(a) == _dump(b)
    # the served heads: production_models() fits what the committed module fits
    weights = H.load_weights()
    served = S.production_models()
    for side in F.SIDES:
        train = [r for r in H.matrix_training_rows(side)
                 if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
        ref = committed.fit_v2(train, side, frame="vm", weights=weights)
        for head in ("skill", "timing"):
            assert _dump(served[side][head]) == _dump(ref[head]), (side, head)
    # and the registration artifact is byte-identical to the committed copy
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "data/efv_v2_assembly.json"],
                       cwd=ROOT)
    assert r.returncode == 0, "data/efv_v2_assembly.json differs from HEAD"


def test_screen_flag_on_offers_the_admitted_column_to_its_head_only(monkeypatch):
    key = f"{H.V2_SCREEN_PREFIX}planted"
    monkeypatch.setattr(H, "V2_SCREEN_CANDIDATES_ON", True)
    monkeypatch.setattr(H, "V2_SCREEN_ADMITTED",
                        {"skill": {"hit": (key,), "pit": ()}, "timing": {"hit": (), "pit": ()}})
    assert H.skill_candidates("hit") == _LIST_SKILL["hit"] + (key,)
    assert H.skill_candidates("pit") == _LIST_SKILL["pit"]
    for side in F.SIDES:
        for (ob, ab), keys in _LIST_TIMING.items():
            assert H.timing_candidates(side, ids_outcome_blind=ob, absence_admitted=ab) == keys
    hit = H.fit_v2(_lv_rows("hit", key=key), "hit", frame="lv", weights=_W, absent_ok=False)
    assert key in hit["skill"]["candidates"] and key in hit["skill"]["keys"]
    assert key not in (hit["timing"] or {}).get("candidates", [])
    pit = H.fit_v2(_lv_rows("pit", seed=12, key=key), "pit", frame="lv", weights=_W,
                   absent_ok=False)
    for head in ("skill", "timing"):
        assert key not in ((pit[head] or {}).get("candidates") or [])
    # a key without the screening prefix is refused
    monkeypatch.setattr(H, "V2_SCREEN_ADMITTED", {"skill": {"hit": ("planted",)}})
    with pytest.raises(ValueError):
        H.skill_candidates("hit")
