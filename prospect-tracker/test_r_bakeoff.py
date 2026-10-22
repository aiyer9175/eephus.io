"""tools/r_bakeoff_lab.py pins (docs/r/R_BAKEOFF.md): the registered constants, the bans, the
read-only cache, the bootstrap, the pair definition, and the results agreeing with the
artifacts once the reads exist. R-dependent tests skip when R is absent."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import r_bakeoff_lab as L  # noqa: E402
import rbridge  # noqa: E402

DOC = ROOT / "docs" / "r" / "R_BAKEOFF.md"
SRC = (ROOT / "tools" / "r_bakeoff_lab.py").read_text(encoding="utf-8")
needs_r = pytest.mark.skipif(not rbridge.available(), reason="R is not installed")


def test_registered_constants():
    doc = DOC.read_text(encoding="utf-8")
    assert L.AGING_LABELS == (2008, 2009, 2010, 2011)
    assert "{2008, 2009, 2010, 2011}" in doc
    assert L.AGING_B == 2000 and L.SEED == 20261022 and L.AGING_ALPHA == 0.025
    assert L.XM_WINTERS == tuple(range(2018, 2025))
    assert L.XM_B == 4000 and L.XM_PERM_SEED == 20261023
    assert L.EFV_B == 4000 and L.EFV_SEED == 20261020
    assert L.EFV_PERM_SEEDS == tuple(range(20261024, 20261044))
    assert L.EFV_PLANT_SEED == 20261044 and L.EFV_PLANT_CORR == 0.70


def test_holdouts_and_reserved_frames_are_never_built():
    assert L.XM_LAST == 2024 and max(L.XM_WINTERS) < 2025
    assert max(L.AGING_LABELS) < 2012          # never a path-shape GATE or CONFIRM season
    assert "run_backtest(" not in SRC and "import backtest" not in SRC
    assert "train_proj_models" not in SRC
    # no grouping, counting or stratifying by consensus-FV level
    assert not re.search(r"(by|per|group\w*)[_ ]?(consensus_)?fv", SRC, re.I)
    assert "T.fv" not in SRC
    # item (c)'s groups never come from the board records (amendment A-1: their coverage
    # encodes the reach outcome)
    assert "asof_records" not in SRC and "load_universe" not in SRC and "_universe()" not in SRC


def test_no_dashes_in_the_bakeoff_sources():
    for p in [DOC, ROOT / "tools" / "r_bakeoff_lab.py", ROOT / "tools" / "rbridge.py",
              *sorted((ROOT / "tools" / "r").glob("*.R"))]:
        t = p.read_text(encoding="utf-8")
        assert "—" not in t and "–" not in t, p.name


def test_cache_is_read_only(tmp_path, monkeypatch):
    import fa_projection as fp
    calls = []

    def fake_fitted(corpus, max_season, use_cache=True, **kw):
        calls.append(use_cache)
        if use_cache:
            fp.pickle.dump({}, open(tmp_path / "x.pkl", "wb"))
        return ("curves", "map")
    monkeypatch.setattr(fp, "fitted_models", fake_fitted)
    with L.fit_cache_read_only():
        assert fp.fitted_models({}, 2020) == ("curves", "map")
        with pytest.raises(L.CacheWriteRefused):
            fp.pickle.dump({}, open(tmp_path / "y.pkl", "wb"))
    assert calls == [True, False]
    assert fp.fitted_models is fake_fitted


def test_cluster_bootstrap_is_paired_and_deterministic():
    rng = np.random.default_rng(0)
    e1, e2 = rng.random(50), rng.random(50)
    w = np.ones(50)
    cl = [i // 5 for i in range(50)]
    a = L.boot_mae({"a": e1, "b": e2}, w, cl, 30, 1)
    b = L.boot_mae({"a": e1, "b": e2}, w, cl, 30, 1)
    assert np.array_equal(a["a"], b["a"]) and np.array_equal(a["b"], b["b"])
    same = L.boot_mae({"a": e1, "b": e1}, w, cl, 30, 1)
    assert np.allclose(same["a"] - same["b"], 0.0)
    d = L.diff_summary(np.linspace(-1, 1, 101), 0.025)
    assert d["lb"] < 0 < d["ub"] and L.tie_word(d) == "ties"


def test_aging_pairs_follow_the_fit_definition():
    """Pairs need the floor in t and t + 1; the value is the regressed WAR rate."""
    league = {2010: {}, 2011: {}}
    hit = [{"mlbam": 1, "season": 2010, "age": 26, "role": "H", "pa": 500, "war": 3.0},
           {"mlbam": 1, "season": 2011, "age": 27, "role": "H", "pa": 400, "war": 2.0},
           {"mlbam": 2, "season": 2010, "age": 30, "role": "C", "pa": 90, "war": 1.0},
           {"mlbam": 2, "season": 2011, "age": 31, "role": "C", "pa": 300, "war": 1.0}]
    pairs = L.aging_pairs({"hit": hit, "pit": [], "league": league})
    assert len(pairs) == 1
    p = pairs[0]
    lg10 = (3.0 + 1.0) / (500 + 90) * 600
    v0 = (3.0 / 500 * 600 * 500 + lg10 * 600) / (500 + 600)
    assert p["v0"] == pytest.approx(v0)
    assert p["L"] == 2011 and p["age1"] == 27 and p["role"] == "H"
    assert p["w"] == pytest.approx(2.0 / (1 / 500 + 1 / 400))


def test_second_read_is_refused(tmp_path, monkeypatch):
    art = tmp_path / "a.json"
    monkeypatch.setitem(L.ARTIFACT, "aging", art)
    L.refuse_second_read("aging")
    art.write_text(json.dumps({"read_done": True}), encoding="utf-8")
    with pytest.raises(SystemExit):
        L.refuse_second_read("aging")


def test_dry_run_never_writes_under_data(tmp_path):
    with pytest.raises(SystemExit):
        L.main(["--item", "aging", "--dry-run", "--out", str(ROOT / "data" / "x.json")])


@needs_r
def test_aging_fixture_runs_end_to_end():
    pairs = L.aging_fixture()
    res = L.aging_read(pairs, None, L.AGING_LABELS, B=50, seed=1)
    for side in ("hit", "pit"):
        assert set(res["score"][side]["mae"]) == {"GAM", "INC", "N0", "N1", "INC_lambda0"}
        assert res["verdict"][side]["verdict"].startswith(("PASS", "FAIL"))
        assert len(res["planted"][side]["curve_rmse_by_fold"]) == 4


@needs_r
def test_glmm_recovers_a_planted_org_effect():
    rng = np.random.default_rng(3)
    n = 2500
    org = rng.integers(0, 25, n)
    eo = rng.normal(0, 0.4, 25)
    off = rng.normal(0, 1, n)
    y = off + eo[org] + rng.normal(0, 1, n)
    job = {"id": "q", "family": "gaussian", "y": y.tolist(), "w": np.ones(n).tolist(),
           "offset": off.tolist(), "org": [f"o{x}" for x in org],
           "ls": [f"l{x % 9}" for x in range(n)], "ec": [f"e{x % 4}" for x in range(n)]}
    r = rbridge.run_r("efv_glmm.R", {"jobs": [job]})["jobs"]["q"]
    est = np.asarray([r["re"]["org"][f"o{i}"] for i in range(25)])
    assert np.corrcoef(est, eo)[0, 1] > 0.9


ART = {k: v for k, v in L.ARTIFACT.items()}


@pytest.mark.parametrize("item", sorted(ART))
def test_results_doc_agrees_with_the_artifact(item):
    """Once an item is read, RESULTS.md quotes its verdict word for word."""
    p = ART[item]
    if not p.exists():
        pytest.skip(f"{item} not read yet")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["read_done"] is True and doc["dry_run"] is False
    res = (ROOT / "docs" / "r" / "RESULTS.md").read_text(encoding="utf-8")
    v = doc["verdict"]
    words = ([v[s]["verdict"] for s in ("hit", "pit")] if item == "aging" else [v["verdict"]])
    for w in words:
        assert w in res, (item, w)
