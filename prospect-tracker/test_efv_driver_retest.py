"""Z1, the fWAR label epoch's driver re-test: the engineering that precedes the registration.

Plan docs/master-plan-2026-09-11-war-epoch-drivers-betting.md section 2.1, "Engineering
first": the `retest` mode in tools/efv_driver_lab.py, which ports the 4-fold-era arms with
bit parity; an `alpha` argument for `holm_family`, with a test; and the mechanically derived
arm list (P5) that tools/efv_arm_ledger.py emits.

WHAT PARITY MEANS HERE, AND WHAT IT DOES NOT. Each ported arm's add column, built by the
retest mode, must reproduce the column the ORIGINAL code builds, bit for bit, on the same
rows. Nothing below fits a model, scores a column or reads a label: a column is not a read,
and the retired 4-fold basis is not reproduced (plan 2.4, "it adjudicates nothing"). Where
the original code can be called it is called (efv_lab_runner._add_feats, run_lab.augment,
efv_ml_lab.run_variant with its fold list emptied, efv_wrc_lab.build_join and inject); the
one deleted producer (tools/efv_weight_recal_lab.py) is read from git at the parent of the
commit that removed it.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_arm_ledger as AL           # noqa: E402
import efv_driver_lab as L             # noqa: E402
import efv_model as E                  # noqa: E402

DB = ROOT / "prospects.db"
needs_db = pytest.mark.skipif(not DB.exists(), reason="prospects.db is not on this box")
REG_DIR = ROOT / "docs" / "efv-2026-10-03"
LIST_PATH = REG_DIR / "z1_arm_list.json"
REG_PATH = REG_DIR / "LABEL_V3_DRIVER_RETEST_GATE.md"


@contextlib.contextmanager
def _keep_cwd():
    cwd = os.getcwd()
    try:
        yield
    finally:
        os.chdir(cwd)


def _lab_runner():
    with _keep_cwd():
        import efv_lab_runner as LAB       # chdirs on import
    return LAB


@pytest.fixture(scope="module")
def derived():
    try:
        return AL.derive_z1_arm_list()
    except subprocess.CalledProcessError as exc:   # no git history on this box
        pytest.skip(f"git history unavailable: {exc}")


def _bits(a) -> bytes:
    return np.asarray(a, dtype=float).tobytes()


# ------------------------------------------------------------------ holm_family alpha
def _holm_hardcoded(rows):
    """holm_family exactly as it stood before the alpha argument (0.05 hardcoded)."""
    from math import erfc, sqrt
    live = [[k, d, sd, d / sd, 0.5 * erfc((d / sd) / sqrt(2))]
            for k, d, sd in rows if sd and d is not None]
    live.sort(key=lambda r: r[4])
    m, still, out = len(live), True, {}
    for i, r in enumerate(live):
        alpha = 0.05 / (m - i)
        surv = bool(still and r[4] <= alpha)
        if not surv:
            still = False
        out[r[0]] = {"delta": round(r[1], 5), "sd": round(r[2], 5), "z": round(r[3], 3),
                     "p_one_sided": round(r[4], 5), "rank": i + 1,
                     "holm_alpha": round(alpha, 5), "survives_holm": surv}
    return out, m


def _rows(seed, n=40):
    rng = random.Random(seed)
    rows = [(f"a{i}.rho", rng.uniform(-0.02, 0.06), rng.uniform(0.004, 0.02))
            for i in range(n)]
    rows.append(("dead.rho", None, 0.01))
    rows.append(("nosd.rho", 0.01, None))
    return rows


@pytest.mark.parametrize("seed", [1, 2, 3, 20260807])
def test_holm_default_is_byte_identical_to_the_hardcoded_form(seed):
    rows = _rows(seed)
    assert json.dumps(L.holm_family(rows)) == json.dumps(_holm_hardcoded(rows))
    assert json.dumps(L.holm_family(rows, alpha=0.05)) == json.dumps(_holm_hardcoded(rows))


@pytest.mark.parametrize("alpha", [0.025, 0.015, 0.005])
def test_holm_alpha_sets_every_step_threshold(alpha):
    rows = _rows(7)
    out, m = L.holm_family(rows, alpha=alpha)
    assert m == 40
    seen_fail = False
    for _k, r in sorted(out.items(), key=lambda kv: kv[1]["rank"]):
        step = alpha / (m - r["rank"] + 1)
        assert r["holm_alpha"] == round(step, 5)
        if seen_fail:
            assert r["survives_holm"] is False, "Holm stops at the first failure"
        if r["survives_holm"]:
            assert r["p_one_sided"] <= round(step, 5) + 5e-6
        else:
            seen_fail = True


@pytest.mark.parametrize("alpha", [0.025, 0.015, 0.005])
def test_holm_alpha_separates_a_step_one_case(alpha):
    """One arm whose one-sided p sits between alpha/m and 0.05/m survives at 0.05 and
    fails at the smaller family level: the alpha argument is live, not decorative."""
    m = 10
    z_mid = None
    from statistics import NormalDist
    lo, hi = alpha / m, 0.05 / m
    p = math.sqrt(lo * hi)
    z_mid = NormalDist().inv_cdf(1 - p)
    rows = [("x.rho", z_mid * 0.01, 0.01)] + [(f"n{i}.rho", -0.01, 0.01) for i in range(m - 1)]
    assert L.holm_family(rows)[0]["x.rho"]["survives_holm"] is True
    assert L.holm_family(rows, alpha=alpha)[0]["x.rho"]["survives_holm"] is False


# ------------------------------------------------------------------ constants pinned
def test_family_alphas_are_the_plan_and_agree_across_the_two_tools():
    plan = {"H-MECH": 0.025, "P-MECH": 0.015, "H-NOMECH": 0.005, "P-NOMECH": 0.005,
            "ABL": 0.05}
    assert L.Z1_FAMILY_ALPHA == plan
    assert AL.Z1_FAMILY_ALPHA == plan


def test_frames_are_the_lab_constants_and_exclude_the_reserved_cohort():
    assert AL.Z1_FRAMES["deb11"]["years"] == list(E.SCORED_YEARS)
    assert AL.Z1_FRAMES["deb6"]["years"] == list(L.EXTRAS_YEARS)
    for f in AL.Z1_FRAMES.values():
        assert max(f["years"]) <= 2024, "the reserved 2025 base-year cohort stays out (2.4)"


# ------------------------------------------------------------------ the derived list
def test_the_list_is_complete_and_partitioned(derived):
    ids = [a["id"] for a in derived["arms"]]
    assert len(ids) == len(set(ids)) == derived["n_arms"]
    fam = {f: v["arms"] for f, v in derived["families"].items()}
    assert sum(fam.values()) == derived["n_arms"]
    for a in derived["arms"]:
        assert a["family"] in AL.Z1_FAMILY_ALPHA
        assert a["frame"] in AL.Z1_FRAMES and a["scope"] in AL.Z1_SCOPES
        assert a["years"] == AL.Z1_FRAMES[a["frame"]]["years"]
        assert a["origins"], a["id"]


def test_every_column_kind_has_a_retest_builder(derived):
    known = {"vec", "expr", "rawtool", "milb", "sbath", "xjoin", "wrc", "extras", "hand",
             "vol", "agex", "health"}
    for a in derived["arms"]:
        for c in a["columns"]:
            assert c["kind"] in known, (a["id"], c)
        if a["family"] == "ABL":
            assert a["columns"] == [] and len(a["drop"]) == 1


def test_abl_drops_every_served_feature_with_fv_as_the_liveness_control(derived):
    abl = [a for a in derived["arms"] if a["family"] == "ABL"]
    for side in ("hit", "pit"):
        served = list(E._feature_spec(side)[0])
        got = [a["drop"][0] for a in abl if a["side"] == side]
        assert sorted(got) == sorted(served)
        ctrl = [a for a in abl if a["side"] == side and a.get("liveness_control")]
        assert [a["drop"] for a in ctrl] == [["fv"]]
    assert derived["families"]["ABL"]["holm_legs"] == 2 * (len(abl) - 2)


def test_mechanism_families_follow_the_declared_tags(derived):
    by = {a["id"]: a for a in derived["arms"]}
    hmech = {a["id"] for a in derived["arms"] if a["family"] == "H-MECH"}
    pmech = {a["id"] for a in derived["arms"] if a["family"] == "P-MECH"}
    for need in ("H-MECH.hit.tool_field", "H-MECH.hit.pos_prem", "H-MECH.hit.dtool_proxy",
                 "H-MECH.hit.field_x_pos", "H-MECH.hit.tool_throw", "H-MECH.hit.athl3",
                 "H-MECH.hit.athl_sf", "H-MECH.hit.athl_st", "H-MECH.hit.defense",
                 "H-MECH.hit.physical"):
        assert need in hmech, need
    for need in ("tool_cmd", "tool_sl", "tool_ch", "era_rel", "starter_shape",
                 "arsenal_depth", "relief_flag", "peak_bb_rel", "sits_mid@deb6",
                 "tops@deb6", "rpm_fb@deb6"):
        assert f"P-MECH.pit.{need}" in pmech, need
    for a in derived["arms"]:
        if any(o.get("era") == "0904" for o in a["origins"]):
            assert a["family"].endswith("NOMECH"), a["id"]
        if a["family"] in ("H-MECH", "P-MECH"):
            assert a["mechanism"], a["id"]
    assert by["H-NOMECH.hit.tool_gap@deb6"]["mechanism"] == []


def test_the_exclusions_are_mechanical(derived):
    rules = {e["rule"] for e in derived["excluded_arms"]}
    assert rules <= {"R-SERVED", "R-SWAP", "R-27", "R-DEGENERATE"}
    for a in derived["arms"]:
        for c in a["columns"]:
            if c["kind"] == "vec":
                assert c["key"] not in E._feature_spec(a["side"])[0], a["id"]
                assert c["key"] != "il_stints_pre"


def test_the_committed_list_is_the_derivation_while_its_sources_stand(derived):
    """Kill rule 1, frozen list. The committed file is what the derivation writes, for as
    long as every source still hashes to what the list recorded. A source that moved after
    the registration does not reopen the list; it skips this test with its name."""
    if not LIST_PATH.exists():
        pytest.skip("the registration has not been committed")
    frozen = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    moved = [s["artifact"] for s, t in zip(frozen["sources"], derived["sources"])
             if s["sha256"] != t["sha256"]]
    if moved:
        pytest.skip(f"sources moved after the registration: {moved}")
    assert json.dumps(derived, indent=1) + "\n" == LIST_PATH.read_text(encoding="utf-8")


def test_the_registration_records_the_lists_sha256():
    if not REG_PATH.exists():
        pytest.skip("the registration has not been committed")
    sha = L._sha256(LIST_PATH)
    assert sha in REG_PATH.read_text(encoding="utf-8")


# ------------------------------------------------------------------ parity, 4-fold era
def _ported(derived, kinds):
    for a in derived["arms"]:
        if "ported_4fold" in a["port"] and all(c["kind"] in kinds for c in a["columns"]):
            yield a


def _pool_cols(arm, ctx=None):
    ctx = ctx or L.Z1Context()
    specs = L.z1_specs(arm, ctx)
    D = L.load_pool(arm["side"], specs)
    return D


def test_vec_and_expression_ports_match_their_producers(derived):
    """Every 4-fold-era vec or expression origin against the code that built it, on the
    same rows, bit for bit: efv_lab_runner._add_feats over efv_model._vec for the
    lab_runner lanes, and efv_model's own feats.get(k, 0.0) for the E1 flag path
    (xfv_repeat_level_eval.json). The deleted weight-recal producer has its own test."""
    from efv_dataset import matrix_path
    LAB = _lab_runner()
    n = 0
    for arm in _ported(derived, {"vec", "expr"}):
        D = _pool_cols(arm)
        raw = {r["player_key"]: r for r in
               json.loads(matrix_path(arm["side"]).read_text(encoding="utf-8"))}
        for o in arm["origins"]:
            if o.get("era") != "4fold" or o["artifact"] == "xfv_weight_recal_eval.json":
                continue
            for j, c in enumerate(arm["columns"]):
                if o["artifact"] == "xfv_repeat_level_eval.json":
                    orig = [E._vec(raw[pk], arm["side"]).get(c["key"], 0.0) for pk in D["pk"]]
                else:
                    expr = c["expr"] if c["kind"] == "expr" else f"g(f,'{c['key']}')"
                    orig = [LAB._add_feats(E._vec(raw[pk], arm["side"]),
                                           [{"name": "__c", "expr": expr}])["__c"]
                            for pk in D["pk"]]
                assert _bits(D["EX"][:, j]) == _bits(orig), (arm["id"], o["arm"], c)
                n += 1
    assert n >= 20


def _deleted_weight_recal_features():
    src = subprocess.check_output(
        ["git", "show", "8fecb2f5^:prospect-tracker/tools/efv_weight_recal_lab.py"],
        cwd=str(ROOT.parent)).decode("utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_added_features")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "efv_weight_recal_lab", "exec"), ns)
    return ns["_added_features"]


def test_weight_recal_ports_match_the_deleted_producer(derived):
    try:
        added = _deleted_weight_recal_features()
    except (subprocess.CalledProcessError, OSError) as exc:
        pytest.skip(f"git history unavailable: {exc}")
    from efv_dataset import matrix_path
    n = 0
    for arm in derived["arms"]:
        for o in arm["origins"]:
            if o["artifact"] != "xfv_weight_recal_eval.json":
                continue
            side, name = o["arm"].split(".", 1)
            fn = added(side)[name]
            D = _pool_cols(arm)
            raw = {r["player_key"]: r for r in
                   json.loads(matrix_path(side).read_text(encoding="utf-8"))}
            orig = [fn(E._vec(raw[pk], side)) for pk in D["pk"]]
            assert _bits(D["EX"][:, 0]) == _bits(orig), (arm["id"], o["arm"])
            n += 1
    assert n == 6


@needs_db
def test_sb_athleticism_ports_match_run_lab(derived):
    LAB = _lab_runner()
    with _keep_cwd():
        spec = importlib.util.spec_from_file_location(
            "z1_run_lab", ROOT / "docs" / "efv-sb-athleticism-2026-08-05" / "run_lab.py")
        run_lab = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_lab)
        try:
            rows, _aug = run_lab.augment()
            orig = {r["player_key"]: dict(r["feats"]) for r in rows}
        finally:
            LAB._CACHE.clear()
    assert L.SBATH_TOOL_Z == run_lab.TOOL_Z
    n = 0
    for arm in derived["arms"]:
        names = {o["arm"] for o in arm["origins"]
                 if o["artifact"] == "docs/efv-sb-athleticism-2026-08-05/results.json"}
        if not names:
            continue
        col = arm["columns"][0]
        key = col["name"] if col["kind"] == "sbath" else col["key"]
        D = _pool_cols(arm)
        assert set(D["pk"]) == set(orig)
        assert _bits(D["EX"][:, 0]) == _bits([orig[pk][key] for pk in D["pk"]]), arm["id"]
        n += 1
    assert n == 6


@needs_db
def test_extra_join_ports_match_efv_ml_lab(derived, monkeypatch):
    LAB = _lab_runner()
    with _keep_cwd():
        import efv_ml_lab as ML
    monkeypatch.setattr(ML, "SCORED_YEARS", ())        # attach the join, fit nothing
    n = 0
    try:
        for arm in derived["arms"]:
            col = arm["columns"][0] if arm["columns"] else {}
            if col.get("kind") != "xjoin":
                continue
            LAB._CACHE.clear()
            ML._EXTRA_CACHE.clear()
            res = ML.run_variant({"id": "z1_parity", "side": arm["side"],
                                  "extra_join": col["join"]})
            assert res.get("error"), "the patched run must not have scored anything"
            orig = {r["player_key"]: r["feats"] for r in LAB.data_for(arm["side"])}
            D = _pool_cols(arm)
            assert set(D["pk"]) == set(orig)
            for j, k in enumerate(col["keys"]):
                name = f"x_{col['join']}_{k}"
                assert _bits(D["EX"][:, j]) == _bits([orig[pk][name] for pk in D["pk"]]), name
                n += 1
    finally:
        LAB._CACHE.clear()
    assert n == 5


@needs_db
def test_wrc_ports_match_efv_wrc_lab(derived):
    LAB = _lab_runner()
    with _keep_cwd():
        import efv_wrc_lab as W
        import wrc_rates
    try:
        LAB._CACHE.clear()
        joined, _meta, _n = W.build_join()
        W.inject(joined, mode="zero")
        rows_c = wrc_rates.load_rows()
        m, last_beta, lg_rate = W.clause_m(rows_c)
        comp = W._composite_feature(rows_c, last_beta, lg_rate) if m.get("passes") else None
        orig = {}
        for r in LAB.data_for("hit"):
            orig[r["player_key"]] = dict(r["feats"])
            if comp is not None:
                orig[r["player_key"]]["wrc_comp"] = float(comp.get(r["player_key"], 0.0))
    finally:
        LAB._CACHE.clear()
    n = 0
    for arm in derived["arms"]:
        col = arm["columns"][0] if arm["columns"] else {}
        if col.get("kind") != "wrc":
            continue
        if col["key"] == "wrc_comp" and comp is None:
            pytest.fail("clause M no longer passes, so the A4 arm cannot be built")
        D = _pool_cols(arm)
        assert set(D["pk"]) == set(orig)
        assert _bits(D["EX"][:, 0]) == _bits([orig[pk][col["key"]] for pk in D["pk"]]), \
            arm["id"]
        n += 1
    assert n == 3


def test_tool_throw_is_flagged_never_measured_and_takes_the_vec_tool_encoding(derived):
    arm = next(a for a in derived["arms"] if a["id"] == "H-MECH.hit.tool_throw")
    assert arm["port"] == ["never_measured"]
    D = _pool_cols(arm)
    from efv_dataset import matrix_path
    raw = {r["player_key"]: r for r in
           json.loads(matrix_path("hit").read_text(encoding="utf-8"))}
    want = [float(raw[pk]["tool_throw"]) if raw[pk].get("tool_throw") is not None else 45.0
            for pk in D["pk"]]
    assert _bits(D["EX"][:, 0]) == _bits(want)


# ------------------------------------------------------------------ retest wiring
def test_drop_and_scope_arguments_default_to_the_old_behaviour():
    D = L.load_pool("pit")
    D2 = L.load_pool("pit", kinds=("debuted",), keep=None)
    assert D["pk"] == D2["pk"] and _bits(D["X"]) == _bits(D2["X"])
    a = L.chain(D, ())
    b = L.chain(D, (), drop=())
    assert all(_bits(x) == _bits(y) for x, y in zip(a, b))


def test_retest_refuses_a_list_that_is_not_the_frozen_one(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps({"arms": [], "frames": AL.Z1_FRAMES}), encoding="utf-8")
    with pytest.raises(SystemExit):
        L.retest_mode(p, B=10, expect_sha="0" * 64)


def test_the_d1_getter_reads_the_same_values_as_the_port(derived):
    """The merged vec arms carry D-1 origins too. D-1 read feats.get(k) with None imputed
    to 0; the port reads efv_lab_runner's g(). Equal in value on every row (IEEE ==), and
    the only bit difference allowed is the sign of a zero."""
    from efv_dataset import matrix_path
    n = 0
    for arm in derived["arms"]:
        if not any(o["artifact"] == "xfv_driver_freekeys.json" for o in arm["origins"]):
            continue
        D = _pool_cols(arm)
        raw = {r["player_key"]: r for r in
               json.loads(matrix_path(arm["side"]).read_text(encoding="utf-8"))}
        key = arm["columns"][0]["key"]
        assert arm["columns"][0]["read"] in ("lab_g", "raw")
        d1 = []
        for pk in D["pk"]:
            v = E._vec(raw[pk], arm["side"]).get(key)
            d1.append(0.0 if v is None else float(v))
        port = D["EX"][:, 0]
        assert np.array_equal(port, np.array(d1)), arm["id"]
        diff = port.view(np.int64) != np.array(d1).view(np.int64)
        assert np.all(port[diff] == 0.0), arm["id"]
        n += 1
    assert n >= 20
