# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV v2 model-class candidates (efv_v2_candidates.py, EFV3_C02;
docs/efv-v2/MODEL_CLASS_SCREEN.md s2). Synthetic rows only: no frame, no label module,
no served artifact is read by a fit here.

1. Imports: efv_v2_model, efv_vintage_frame and source_backtest only; no label module
   loads on import; no WAR column is read off a row; no FV-cell grouping (the
   test_efv_v2_model.py scan applied to the new file); no em-dash.
2. Every fit is bit-reproducible on a second call.
3. MC-1: a reversed target flips every slope; pairs never cross decision_year or side.
4. MC-2: the reliability table for V reads no row at or after V - 2; a row without a
   source carries no indicator column.
5. MC-3: band weights come only from rows at or before RULE_LAST_YEAR; a no-block row
   takes the lower band.
6. MC-4a: no fitted slope opposes its admitted sign (and nothing moves when none does).
7. MC-4b: every spline basis is non-decreasing in the admitted direction; the fallback.
8. MC-5: order_idx bit-identical with and without the pricing term.
9. The absence flag is refused in every skill design; a reserved vintage or a 2025+
   year raises before any fit.
10. The assembly tool's fold sign receipt (a read of the artifact).
"""
from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_v2_candidates as C
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_v2_candidates.py"
sys.path.insert(0, str(ROOT / "tools"))

WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}
SINGLE_SOURCE = {"k": 0.5, "prior": 35.0}   # consensus.SINGLE_SOURCE_K / _PRIOR
_LABEL_MODULES = {"efv_labels", "war_source", "ewar", "ewar_v2", "fwar"}
_LABEL_COLUMNS = {"war", "career_war", "l6", "w2", "w3", "r3", "fwar", "ewar", "bwar",
                  "outcome", "war_seasons"}


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


def _rows(side="hit", years=range(2011, 2020), n=150, seed=11, frame="lv", *,
          collinear=False, speed_neg=False, grades=False, block_share=1.0):
    """Rows shaped like efv_v2_model.fit_v2's: a planted driver (hitters tool_hit,
    pitchers k_rel); consensus explains part of the target. `collinear` plants
    obp_rel as a proxy of tool_hit whose own noise hurts the target, so its admitted
    sign is positive while its joint slope is negative. `speed_neg` plants tool_speed
    with a negative effect. `grades` attaches per-source grades for MC-2."""
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            ts = float(rng.normal(48, 6))
            kr = float(rng.normal(0, 0.05))
            e = float(rng.normal(0, 0.03))
            obp = (0.02 * (th - 50) + e) if collinear else float(rng.normal(0, 0.03))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            if collinear:
                drv -= 2.0 * e
            if speed_neg:
                drv -= 0.05 * (ts - 48)
            t = 0.1 * (fv - 45) + drv + float(rng.normal(0, 1))
            block = bool(rng.random() < block_share)
            feats = _feats(block, tool_hit=th, tool_speed=ts, k_rel=kr, peak_k_rel=kr,
                           obp_rel=obp, level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2),
                     "nov_add": float(rng.random() < 0.1)}
            row = {"player_key": f"{side}{i}", "decision_year": yr, "fv": fv,
                   "target": t, "reached": float(t > 0.5), "weight": 1.0,
                   "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                   "frame": frame, "ids_outcome_blind": frame == "lv"}
            if grades:
                g = {}
                if rng.random() < 0.9:
                    g["fangraphs"] = fv + float(rng.normal(0, 3))
                if rng.random() < 0.7:
                    g["mlb_pipeline"] = fv + float(rng.normal(0, 2))
                row["grades"] = g
            out.append(row)
            i += 1
    return out


def _by_vintage(rows):
    out: dict = {}
    for r in rows:
        out.setdefault(int(r["decision_year"]), []).append(r)
    return out


def _reliability(rows, targets=range(2011, 2018)):
    return C.build_source_reliability({"hit": _by_vintage(rows)},
                                      single_source=SINGLE_SOURCE,
                                      target_vintages=list(targets))


def _dump(m):
    return json.dumps(m, sort_keys=True, default=str)


@pytest.fixture(scope="module")
def train():
    return _rows(years=range(2011, 2017), n=150)


@pytest.fixture(scope="module")
def test_rows():
    return _rows(years=[2017], seed=99)


# ---------------------------------------------------------------------------
# 1. imports, label bans, FV-cell scan, copy
# ---------------------------------------------------------------------------

def _imports(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def test_imports_are_the_allowed_set():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    got = _imports(tree)
    assert got <= {"__future__", "math", "numpy", "efv_v2_model", "efv_vintage_frame",
                   "source_backtest"}, got
    assert {"efv_v2_model", "efv_vintage_frame", "source_backtest"} <= got
    assert not got & _LABEL_MODULES


def test_importing_the_module_loads_no_label_module():
    code = ("import sys, efv_v2_candidates; "
            "print(','.join(sorted(m for m in sys.modules "
            "if m.split('.')[0] in %r)))" % sorted(_LABEL_MODULES))
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", r.stdout


def test_no_war_column_is_read_off_a_row():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            assert node.slice.value not in _LABEL_COLUMNS, (node.slice.value, node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get":
            for a in node.args:
                if isinstance(a, ast.Constant):
                    assert a.value not in _LABEL_COLUMNS, (a.value, node.lineno)


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


def test_no_fv_cell_grouping():
    """test_efv_v2_model.py's scan, applied to the new file (no exemption: the module
    defines no row-count constant on the grade grid)."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for name in _names(tree):
        assert not any(t in name.lower() for t in _BANNED_TOKENS), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value


@pytest.mark.parametrize("path", ["efv_v2_candidates.py", "test_efv_v2_candidates.py",
                                  "tools/efv_v2_assemble.py"])
def test_no_em_dash(path):
    txt = (ROOT / path).read_text(encoding="utf-8")
    assert chr(0x2014) not in txt and chr(0x2013) not in txt


def test_flag_is_off_and_fit_v2_does_not_read_it():
    assert C.V2_SIGN_CONSTRAINED is False
    assert "V2_SIGN_CONSTRAINED" not in (ROOT / "efv_v2_model.py").read_text(encoding="utf-8")


def test_model_ids():
    assert C.FAMILY == ("mc1", "mc2", "mc3", "mc4a", "mc4b")
    for arm in C.FAMILY + ("mc5",):
        assert C.ARM_IDS[arm] == f"efv_v2_mc_{arm[2:]}"


# ---------------------------------------------------------------------------
# 2. bit-reproducible
# ---------------------------------------------------------------------------

def _fit_all(train):
    g = _rows(years=range(2011, 2017), n=150, grades=True)
    rel = _reliability(g)
    bw = C.band_weights("hit", {"lv": train}, absent_ok=False)
    fams = ["corner", "middle", "other"] * (len(train) // 3) + ["other"] * (len(train) % 3)
    ages = [20.0 + (i % 7) for i in range(len(train))]
    return {
        "mc1": C.fit_mc1_pairwise(train, "hit", "lv", WEIGHTS, absent_ok=False),
        "mc2": C.fit_mc2_anchor(g, "hit", "lv", WEIGHTS, rel, absent_ok=False),
        "mc3": C.fit_mc3_twoband(train, "hit", "lv", bw["weights"], absent_ok=False),
        "mc4a": C.fit_mc4a_signed(train, "hit", "lv", WEIGHTS, absent_ok=False),
        "mc4b": C.fit_mc4b_spline(train, "hit", "lv", WEIGHTS, absent_ok=False),
        "mc5": C.fit_mc5_pricing(train, fams, ages, side="hit"),
    }


def test_every_fit_is_bit_reproducible(train):
    a = _fit_all(train)
    b = _fit_all(train)
    for arm in a:
        assert _dump(a[arm]) == _dump(b[arm]), arm
        assert a[arm]["model_id"] == C.ARM_IDS[arm]


def test_predict_matches_predict_v2_on_a_v2_model(train, test_rows):
    base = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    assert C._predict(base, test_rows) == H.predict_v2(base, test_rows)


# ---------------------------------------------------------------------------
# 3. MC-1
# ---------------------------------------------------------------------------

def test_mc1_reversed_target_flips_every_slope(train):
    m = C.fit_mc1_pairwise(train, "hit", "lv", WEIGHTS, alpha=10.0, absent_ok=False)
    head = m["skill"]
    assert head["loss"] == "bradley_terry" and head["n_pairs"] > 0
    assert head["b_uc"] > 0 and all(b != 0 for b in head["beta"])
    rev = [dict(r, target=-r["target"]) for r in train]
    mr = C.fit_mc1_pairwise(rev, "hit", "lv", WEIGHTS, alpha=10.0, absent_ok=False)
    hr = mr["skill"]
    assert hr["keys"] == head["keys"]
    assert np.sign(hr["b_uc"]) == -np.sign(head["b_uc"])
    for b, br in zip(head["beta"], hr["beta"]):
        assert np.sign(br) == -np.sign(b) and br != 0


def test_mc1_pairs_never_cross_decision_year_or_side(train):
    mixed = [dict(r, side="hit" if i % 2 else "pit") for i, r in enumerate(train)]
    pr = C.mc1_pairs(mixed, "hit")
    assert pr["n_pairs"] > 0 and pr["i"].size == pr["j"].size == pr["weight"].size
    _u, u_y = H._percentiles(mixed)
    rows = [mixed[k] for k in pr["row_index"]]
    for i, j, w in zip(pr["i"], pr["j"], pr["weight"]):
        assert rows[i]["decision_year"] == rows[j]["decision_year"]
        assert rows[i]["side"] == rows[j]["side"]
        assert w > 0 and u_y[pr["row_index"][i]] > u_y[pr["row_index"][j]]
    # every pair lives in one group of the index
    assert sum(pr["n_pairs_by_group"].values()) == pr["n_pairs"]
    # ties contribute nothing: a constant target gives no pair
    flat = [dict(r, target=0.0) for r in train]
    assert C.mc1_pairs(flat, "hit")["n_pairs"] == 0
    # the listwise sensitivity is a weighting of the same pairs
    lw = C.mc1_pairs(mixed, "hit", weighting="listwise")
    assert lw["n_pairs"] == pr["n_pairs"] and np.all(lw["weight"] <= pr["weight"] + 1e-12)


def test_mc1_is_v2_without_an_admitted_skill_driver():
    flip = _rows("pit", years=range(2011, 2017))
    for r in flip:
        if r["decision_year"] == 2014:
            r["target"] = -r["target"]
    m = C.fit_mc1_pairwise(flip, "pit", "lv", WEIGHTS, absent_ok=False)
    assert m["skill"] is None and m["consensus_only"] and "DS-Q2" in m["consensus_only_reason"]


# ---------------------------------------------------------------------------
# 4. MC-2
# ---------------------------------------------------------------------------

def test_mc2_reliability_table_reads_nothing_at_or_after_v_minus_2():
    rows = _rows(years=range(2011, 2020), n=150, grades=True)
    rel = _reliability(rows, targets=range(2011, 2020))
    for V, read in rel["reads"]["hit"].items():
        assert all(int(v) <= int(V) - C.RELIABILITY_LAG for v in read), (V, read)
        assert not any(int(v) >= int(V) - 2 for v in read)
    assert rel["reads"]["hit"]["2017"] == [2011, 2012, 2013, 2014]
    # poisoning every row at or after V - 2 leaves the table for V unchanged
    V = 2017
    poisoned = [dict(r, target=1e6 * (i % 5), grades={k: 99.0 - (i % 9)
                                                      for k in r["grades"]})
                if r["decision_year"] >= V - 2 else r for i, r in enumerate(rows)]
    again = _reliability(poisoned, targets=[V])
    assert again["table"]["hit"][str(V)] == rel["table"]["hit"][str(V)]
    # the shipped shrink and clamp, and equal weight with no history
    assert rel["shrink_k"] == 150 and rel["clamp"] == [0.6, 1.5]
    assert rel["table"]["hit"]["2011"] == {"fangraphs": 1.0, "mlb_pipeline": 1.0}
    for w in rel["table"]["hit"]["2017"].values():
        assert 0.6 <= w <= 1.5


def test_mc2_row_without_a_source_carries_no_indicator():
    rows = _rows(years=range(2011, 2017), n=150, grades=True)
    rel = _reliability(rows)
    m = C.fit_mc2_anchor(rows, "hit", "lv", WEIGHTS, rel, absent_ok=False)
    assert m["model_id"] == "efv_v2_mc_2" and m["anchor"]["indicator_columns"] == []
    for head in (m["skill"], m["timing"]):
        if head is None:
            continue
        assert head["anchor"] is True
        for k in head["keys"]:
            assert not k.startswith("has_") and k not in rel["sources"]["hit"]
            assert k in H.skill_candidates("hit") + H.timing_candidates(
                "hit", ids_outcome_blind=True)
    # the anchor of a row missing a source is the weighted mean over its present
    # sources only; a one-source row's grade is first shrunk as consensus shrinks it
    u, n_missing = C.anchor_values(rows, rel, "hit")
    assert n_missing == sum(1 for r in rows if not r["grades"])
    V = 2016
    idx = [i for i, r in enumerate(rows) if r["decision_year"] == V]
    w = rel["table"]["hit"][str(V)]
    w_src = 1.0 / (1.0 + SINGLE_SOURCE["k"])
    pct = {}
    for s in rel["sources"]["hit"]:
        have = [i for i in idx if s in rows[i]["grades"]]
        vals = [(w_src * rows[i]["grades"][s] + (1 - w_src) * SINGLE_SOURCE["prior"])
                if len(rows[i]["grades"]) == 1 else rows[i]["grades"][s] for i in have]
        pct[s] = dict(zip(have, H.within_pct(vals, [0] * len(have))))
    one = next(i for i in idx if len(rows[i]["grades"]) == 1)
    two = next(i for i in idx if len(rows[i]["grades"]) == 2)
    s1 = next(iter(rows[one]["grades"]))
    assert u[one] == pytest.approx(pct[s1][one])
    assert u[two] == pytest.approx(sum(w[s] * pct[s][two] for s in w) / sum(w.values()))
    # with every source present and equal weights the anchor is the mean percentile
    none = next((i for i in idx if not rows[i]["grades"]), None)
    if none is not None:
        assert u[none] == pytest.approx(H.within_pct([r["fv"] for r in rows],
                                                     [r["decision_year"] for r in rows])[none])


def test_mc2_predict_uses_the_rows_own_anchor():
    rows = _rows(years=range(2011, 2017), n=150, grades=True)
    te = _rows(years=[2017], seed=5, grades=True)
    rel = _reliability(rows)
    m = C.fit_mc2_anchor(rows, "hit", "lv", WEIGHTS, rel, absent_ok=False)
    out = C.predict_mc2(m, te)
    u, _n = C.anchor_values(te, rel, "hit")
    assert [o["u_c"] for o in out] == [float(x) for x in u]
    assert sorted(o["efv_grade"] for o in out) == pytest.approx(sorted(r["fv"] for r in te))


# ---------------------------------------------------------------------------
# 5. MC-3
# ---------------------------------------------------------------------------

def test_mc3_band_weights_read_only_rule_years():
    rows = _rows(years=range(2011, 2020), n=150)
    bw = C.band_weights("hit", {"lv": rows}, absent_ok=False)
    assert bw["years_read"] and max(bw["years_read"]) <= H.RULE_LAST_YEAR
    poisoned = [dict(r, target=1e6 * (i % 7), reached=float(i % 2),
                     v2=dict(r["v2"], tool_hit=-999.0))
                if r["decision_year"] > H.RULE_LAST_YEAR else r
                for i, r in enumerate(rows)]
    again = C.band_weights("hit", {"lv": poisoned}, absent_ok=False)
    assert again["weights"] == bw["weights"]
    for band in C.MC3_BANDS:
        for k in ("w_skill", "w_time"):
            assert 0.0 <= bw["weights"][band]["hit"][k] <= 1.0
    with pytest.raises(ValueError):
        C.band_weights("hit", {"lv": rows}, last_year=H.RULE_LAST_YEAR + 1)


def test_mc3_no_block_row_takes_the_lower_band():
    import efv_dataset
    assert C.MC3_BAND_AA_RANK == efv_dataset._LEVEL_RANK["AA"]
    aa = {"v2": H.v2_row(_feats(True, level_rank=float(efv_dataset._LEVEL_RANK["AA"])))}
    aaa = {"v2": H.v2_row(_feats(True, level_rank=float(efv_dataset._LEVEL_RANK["AAA"])))}
    aplus = {"v2": H.v2_row(_feats(True, level_rank=float(efv_dataset._LEVEL_RANK["A+"])))}
    noblock = {"v2": H.v2_row(_feats(False, level_rank=float(efv_dataset._LEVEL_RANK["AAA"])))}
    assert C.band_of_row(aa) == "upper" and C.band_of_row(aaa) == "upper"
    assert C.band_of_row(aplus) == "lower" and C.band_of_row(noblock) == "lower"
    assert noblock["v2"]["level_rank"] is None
    train = _rows(years=range(2011, 2017), block_share=0.8)
    te = _rows(years=[2017], seed=4, block_share=0.8)
    bw = {"upper": {"hit": {"w_skill": 1.0, "w_time": 0.0}},
          "lower": {"hit": {"w_skill": 0.25, "w_time": 0.0}}}
    m = C.fit_mc3_twoband(train, "hit", "lv", bw, absent_ok=False)
    assert m["model_id"] == "efv_v2_mc_3" and m["band_weights"]["lower"]["w_skill"] == 0.25
    out = C.predict_mc3(m, te)
    for r, o in zip(te, out):
        w = m["band_weights"][C.band_of_row(r)]["w_skill"]
        assert o["order_idx"] == pytest.approx(o["u_c"] + w * o["e_skill"])
        if not r["v2"]["has_block"]:
            assert C.band_of_row(r) == "lower"


# ---------------------------------------------------------------------------
# 6. MC-4a
# ---------------------------------------------------------------------------

def test_mc4a_no_fitted_slope_opposes_its_admitted_sign():
    train = _rows(years=range(2011, 2017), n=200, collinear=True)
    base = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    signs = C.admitted_signs(base["skill"])
    assert {"obp_rel", "tool_hit"} <= set(base["skill"]["keys"])
    assert signs["obp_rel"] == 1 and signs["tool_hit"] == 1
    # the unconstrained joint slope on the proxy opposes its admitted sign
    opposing = [k for k, b in zip(base["skill"]["keys"], base["skill"]["beta"])
                if signs.get(k, 0) * b < 0]
    assert "obp_rel" in opposing
    m = C.fit_mc4a_signed(train, "hit", "lv", WEIGHTS, absent_ok=False)
    assert m["model_id"] == "efv_v2_mc_4a"
    for head in (m["skill"], m["timing"]):
        if head is None:
            continue
        for k, b in zip(head["keys"], head["beta"]):
            assert head["signs"].get(k, 0) * b >= 0, (k, b)
    assert "obp_rel" in m["constrained_zero"]["skill"]
    assert "obp_rel" not in m["skill"]["keys"] and "tool_hit" in m["skill"]["keys"]
    assert m["skill"]["alpha"] == base["skill"]["alpha"]


def test_mc4a_is_v2_when_no_slope_opposes(train):
    base = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    m = C.fit_mc4a_signed(train, "hit", "lv", WEIGHTS, absent_ok=False)
    assert m["constrained_zero"] == {"skill": {}, "timing": {}}
    for head in ("skill", "timing"):
        if base[head] is None:
            assert m[head] is None
            continue
        assert {k: v for k, v in m[head].items() if k not in ("signs", "constrained_zero")} \
            == base[head]
    te = _rows(years=[2017], seed=99)
    assert C.predict_mc4a(m, te) == H.predict_v2(base, te)


# ---------------------------------------------------------------------------
# 7. MC-4b
# ---------------------------------------------------------------------------

def test_mc4b_basis_is_non_decreasing_in_the_admitted_direction():
    train = _rows(years=range(2011, 2017), n=150, speed_neg=True)
    m = C.fit_mc4b_spline(train, "hit", "lv", WEIGHTS, absent_ok=False)
    assert m["model_id"] == "efv_v2_mc_4b" and m["fell_back"] is False
    head = m["skill"]
    assert head["design"]["kind"] == "ispline"
    assert head["signs"]["tool_hit"] == 1 and head["signs"]["tool_speed"] == -1
    assert "tool_speed" in head["drivers"]
    for k in head["drivers"]:
        s = head["signs"][k]
        lo, _t1, _t2, hi = head["design"]["knots"][k]
        grid = np.linspace(lo - 1.0, hi + 1.0, 501)        # in the admitted direction
        B = C.ispline_basis(grid, head["design"]["knots"][k])
        assert B.shape[1] == C.MC4B_PIECES
        assert np.all(np.diff(B, axis=0) >= 0)
        assert np.all(B[0] == 0.0) and np.all(B[-1] == 1.0)
        # on the raw driver the basis runs with the admitted sign
        raw = np.sort(s * grid)
        Braw = C.ispline_basis(s * raw, head["design"]["knots"][k])
        assert np.all(s * np.diff(Braw, axis=0) >= 0)
    # the fitted contribution is monotone: every kept basis coefficient is non-negative
    assert all(b >= 0 for b in head["beta"])
    # knots at the training terciles of the has-block rows, in the admitted direction
    hb = H.skill_training_rows(train)
    x = np.array([head["signs"]["tool_hit"] * r["v2"]["tool_hit"] for r in hb])
    q = np.quantile(x, C.MC4B_KNOT_QUANTILES)
    assert head["design"]["knots"]["tool_hit"] == [float(x.min()), float(q[0]),
                                                   float(q[1]), float(x.max())]
    out = C.predict_mc4b(m, _rows(years=[2017], seed=99))
    assert any(o["e_skill"] != 0 for o in out)


def test_mc4b_falls_back_to_mc4a_under_the_row_floor():
    train = _rows(years=range(2011, 2017), n=40)
    assert len(H.skill_training_rows(train)) < C.MC4B_MIN_HAS_BLOCK_ROWS
    m = C.fit_mc4b_spline(train, "hit", "lv", WEIGHTS, absent_ok=False)
    assert m["model_id"] == "efv_v2_mc_4b" and m["arm"] == "mc4b"
    assert m["fell_back"] is True and m["fallback"] == "mc4a"
    a = C.fit_mc4a_signed(train, "hit", "lv", WEIGHTS, absent_ok=False)
    assert (m["skill"], m["timing"]) == (a["skill"], a["timing"])
    te = _rows(years=[2017], seed=99)
    assert C.predict_mc4b(m, te) == C.predict_mc4a(a, te)


# ---------------------------------------------------------------------------
# 8. MC-5
# ---------------------------------------------------------------------------

def test_mc5_order_idx_bit_identical_with_and_without_the_pricing_term(train, test_rows):
    rng = np.random.default_rng(3)
    fams = [str(rng.choice(["corner", "middle", "other"])) for _ in train]
    ages = [float(rng.normal(21, 2)) for _ in train]
    pr = C.fit_mc5_pricing(train, fams, ages, side="hit")
    assert pr["model_id"] == "efv_v2_mc_5" and pr["reference_family"] == "corner"
    assert set(pr["family"]) == {"middle", "other"} and pr["age_used"]
    assert pr["columns"] == ["intercept", "fv", "family:middle", "family:other",
                             "age_at_read"]
    base = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    m = C.attach_mc5(base, pr)
    ft = [str(rng.choice(["corner", "middle", "other", None])) for _ in test_rows]
    at = [None if i % 9 == 0 else float(rng.normal(21, 2)) for i in range(len(test_rows))]
    with_term = C.predict_mc5(m, test_rows, ft, at)
    without = H.predict_v2(base, test_rows)
    for key in ("u_c", "e_skill", "e_time", "order_idx", "efv_grade"):
        assert [o[key] for o in with_term] == [o[key] for o in without], key
    assert [o["efv_war_v2"] for o in with_term] == [o["efv_war"] for o in without]
    assert any(o["efv_war"] != o["efv_war_v2"] for o in with_term)
    # a line in the grade with additive shifts: two rows of one family differ by b * dg
    i, j = [k for k, f in enumerate(ft) if f == "middle" and at[k] is not None][:2]
    dg = with_term[i]["efv_grade"] - with_term[j]["efv_grade"]
    da = at[i] - at[j]
    assert with_term[i]["efv_war"] - with_term[j]["efv_war"] == pytest.approx(
        pr["b"] * dg + pr["age"] * da)
    assert C.position_family("SS", "hit") == "middle" and C.position_family("LF", "hit") == "corner"
    assert C.position_family("2B", "hit") == "other" and C.position_family(None, "hit") == "other"
    assert C.position_family("RHP", "pit") == "sp" and C.position_family("RHRP", "pit") == "rp"


# ---------------------------------------------------------------------------
# 9. the absence flag; reserved frames
# ---------------------------------------------------------------------------

def _every_arm(train, side="hit", frame="lv"):
    g = [dict(r, grades={"fangraphs": r["fv"]}) for r in train]
    rel = {"lag": 3, "sources": {side: ["fangraphs"]}, "single_source": SINGLE_SOURCE,
           "table": {side: {str(y): {"fangraphs": 1.0} for y in range(2000, 2030)}}}
    bw = {"upper": WEIGHTS, "lower": WEIGHTS}
    return [lambda: C.fit_mc1_pairwise(train, side, frame, WEIGHTS, absent_ok=False),
            lambda: C.fit_mc2_anchor(g, side, frame, WEIGHTS, rel, absent_ok=False),
            lambda: C.fit_mc3_twoband(train, side, frame, bw, absent_ok=False),
            lambda: C.fit_mc4a_signed(train, side, frame, WEIGHTS, absent_ok=False),
            lambda: C.fit_mc4b_spline(train, side, frame, WEIGHTS, absent_ok=False)]


def test_absence_flag_is_refused_in_every_skill_design(train, monkeypatch):
    monkeypatch.setitem(H.V2_SKILL_KEYS, "hit", H.V2_SKILL_KEYS["hit"] + (H.V2_ABSENCE_KEY,))
    with pytest.raises(ValueError):
        H.skill_keys("hit")
    for fit in _every_arm(train):
        with pytest.raises(ValueError):
            fit()
    # the generic skill fit refuses it in any design, column or driver
    means = H.has_block_means(train)

    def bad_design(rows, _means):
        return np.zeros((len(rows), 1)), [H.V2_ABSENCE_KEY], {"design": {"kind": "v2"}}
    with pytest.raises(ValueError):
        C._skill_fit_g(train, (H.V2_ABSENCE_KEY,), 10.0, bad_design)
    with pytest.raises(ValueError):
        C._skill_fit_g(train, ("x",), 10.0,
                       C._ispline_design((H.V2_ABSENCE_KEY,), {H.V2_ABSENCE_KEY: 1}))
    assert means  # the means were computable: the refusal is the design's, not the rows'


@pytest.mark.parametrize("years,frame", [((2020,), "lv"), ((2021,), "lv"),
                                         ((2025,), "lv"), ((2025,), "vm"),
                                         ((2024, 2026), "vm")])
def test_reserved_vintage_or_2025_year_raises_before_any_fit(years, frame, monkeypatch):
    rows = _rows(years=years, n=80, frame=frame)
    calls = []
    monkeypatch.setattr(H, "fit_v2", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(H, "_skill_fit", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(H, "_timing_fit", lambda *a, **k: calls.append(1))
    for fit in _every_arm(rows, frame=frame):
        with pytest.raises(F.ReservedFrameError):
            fit()
    assert calls == []
    with pytest.raises(F.ReservedFrameError):
        C.guard_training_rows(rows, frame)
    if max(years) >= F.R_VM_FIRST_DEBUT_YEAR:
        with pytest.raises(F.ReservedFrameError):
            C.fit_mc5_pricing(rows, [None] * len(rows), [None] * len(rows), side="hit")
        with pytest.raises(F.ReservedFrameError):
            C.build_source_reliability({"hit": _by_vintage(rows)}, single_source=SINGLE_SOURCE)
    else:
        with pytest.raises(F.ReservedFrameError):
            C.build_source_reliability({"hit": {2017: rows}}, single_source=SINGLE_SOURCE,
                                       target_vintages=list(years))


def test_guard_passes_development_rows(train):
    assert C.guard_training_rows(train, "lv") == list(range(2011, 2017))
    assert C.guard_training_rows(train, "vm") == list(range(2011, 2017))
    with pytest.raises(ValueError):
        C.guard_training_rows(train, "debut")


# ---------------------------------------------------------------------------
# 10. the fold sign receipt (tools/efv_v2_assemble.py)
# ---------------------------------------------------------------------------

def _synthetic_assembly():
    arms = {
        "V2-LV:hit.skill.tool_hit": {"per_vintage_signs": {"2015": 1, "2016": 1},
                                     "by_fold": {"2017": {"per_vintage_signs": {"2015": 1}}}},
        "V2-LV:hit.skill.obp_rel": {"per_vintage_signs": {"2015": 1, "2016": -1},
                                    "by_fold": {"2017": {"per_vintage_signs": {"2015": 1}}}},
        "V2-LV:hit.timing.nov_add": {"per_vintage_signs": {"2015": -1, "2016": -1},
                                     "by_fold": {}},
    }
    folds = {"lv": {"hit": {"2017": {
        "skill": {"keys": ["tool_hit", "obp_rel"], "beta": [0.05, -0.01], "b_uc": 0.2},
        "timing": {"keys": ["nov_add"], "beta": [0.3], "b_uc": 2.0}}}},
        "vm": {"hit": {"2020": {
            "skill": {"keys": ["tool_hit", "obp_rel"], "beta": [-0.02, 0.01], "b_uc": 0.3},
            "timing": None}}}}
    return {"arms": arms, "folds": folds, "code": {"commit": "abc"}}


def test_fold_sign_receipt_classifies_slopes():
    import efv_v2_assemble as A
    rec = A.fold_sign_receipt(_synthetic_assembly())
    by = {(r["frame"], r["key"]): r for r in rec["rows"]}
    assert by[("lv", "tool_hit")]["kind"] == "global_sign" and by[("lv", "tool_hit")]["opposes"] is False
    assert by[("lv", "obp_rel")]["kind"] == "per_fold_admission"
    assert by[("lv", "obp_rel")]["fold_sign"] == 1 and by[("lv", "obp_rel")]["opposes"] is None
    assert by[("lv", "nov_add")]["kind"] == "global_sign" and by[("lv", "nov_add")]["opposes"] is True
    assert by[("vm", "tool_hit")]["kind"] == "single_sign_lv_arm"
    assert by[("vm", "tool_hit")]["opposes_lv_sign"] is True
    assert by[("vm", "tool_hit")]["stored_admitted_sign"] is None
    assert by[("vm", "tool_hit")]["label"] == A.VM_SIGN_LABEL
    assert by[("vm", "obp_rel")]["kind"] == "mixed_sign_lv_arm"
    assert rec["totals"]["lv"] == {"n_slopes": 3, "n_global_sign": 2, "n_global_sign_opposing": 1,
                                   "n_per_fold_admission": 1, "n_no_arm": 0}
    assert rec["totals"]["vm"] == {"n_slopes": 2, "n_stored_admitted_sign": 0,
                                   "n_single_sign_lv_arm": 1, "n_opposing_lv_sign": 1,
                                   "n_mixed_sign_lv_arm": 1, "n_no_arm": 0}
    assert rec["statement"] == A.VM_SIGN_STATEMENT
    assert "cannot be stored until fit_v2 records them" in rec["statement"]


def test_fold_sign_receipt_reads_the_committed_artifact_without_changing_it():
    import efv_v2_assemble as A
    p = ROOT / "data" / "efv_v2_assembly.json"
    if not p.exists():
        pytest.skip("data/efv_v2_assembly.json not built")
    before = p.read_bytes()
    doc = json.loads(before.decode("utf-8"))
    rec = A.fold_sign_receipt(doc)
    assert p.read_bytes() == before
    n_lv = sum(len(h["beta"]) for s in doc["folds"]["lv"].values() for f in s.values()
               for h in (f["skill"], f["timing"]) if h)
    n_vm = sum(len(h["beta"]) for s in doc["folds"]["vm"].values() for f in s.values()
               for h in (f["skill"], f["timing"]) if h)
    t = rec["totals"]
    assert t["lv"]["n_slopes"] == n_lv == (t["lv"]["n_global_sign"]
                                           + t["lv"]["n_per_fold_admission"]
                                           + t["lv"]["n_no_arm"])
    assert t["vm"]["n_slopes"] == n_vm == (t["vm"]["n_single_sign_lv_arm"]
                                           + t["vm"]["n_mixed_sign_lv_arm"]
                                           + t["vm"]["n_no_arm"])
    assert t["vm"]["n_stored_admitted_sign"] == 0
    assert all(r["label"] == A.VM_SIGN_LABEL and r["stored_admitted_sign"] is None
               for r in rec["rows"] if r["frame"] == "vm")
    assert all(r["arm"].startswith("V2-LV:") for r in rec["rows"] if r["arm"])
    assert not any(k.startswith("V2-VM:") for k in doc["arms"])
    for r in rec["rows"]:
        if r["kind"] == "global_sign":
            assert r["opposes"] == (r["sign"] * r["beta"] < 0)
        if r["kind"] == "per_fold_admission":
            assert r["opposes"] is None and len(set(
                r["lv_arm_per_vintage_signs"].values())) > 1
