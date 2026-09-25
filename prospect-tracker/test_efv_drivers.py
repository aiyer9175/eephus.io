# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-07 and EV-08 pins (docs/efv-v2/PROGRAM.md s3.2 D1 and D3, s3.4).

1. efv_drivers imports no label module, directly or through its imports, and reads no
   WAR column: the source names none, and poisoning every WAR-like field on the input
   records leaves every output unchanged.
2. The revision front-runner is forward-chained: changing any read after V leaves the
   prediction for V unchanged, while an earlier read moves it.
3. The reserved guard holds on every entry point, including the V + 1 target read.
4. The 40-man and contract-selection readers respect the as-of cutoff, on synthetic
   histories and on the stored table for a development frame.
5. No FV-cell grouping anywhere in the module (PROSPECT_ANCHOR_GATE).

Real-data tests read development vintages only and compute no grade-vs-outcome figure.
"""
from __future__ import annotations

import ast
import copy
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

import efv_drivers as DR
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_drivers.py"
DATA = ROOT / "data"
_HAVE_DATA = all((DATA / f).exists() for f in ("debuts.json", "inactive.json",
                                                "timeseries.json"))
#: Modules that compute or carry a WAR label. None may load, directly or transitively.
_LABEL_MODULES = {"efv_labels", "war_source", "ewar", "ewar_v2", "fwar"}
#: Not label modules, but they read MLB outcome columns; the driver may not import them.
_NO_DIRECT = _LABEL_MODULES | {"stats", "efv_model"}


# ---------------------------------------------------------------------------
# 1. no label module, no WAR column
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
    allowed = {"__future__", "math", "json", "sys", "numpy", "scipy",
               "efv_vintage_frame", "source_backtest", "storage"}
    got = _imports(tree)
    assert got <= allowed, got - allowed
    assert not got & _NO_DIRECT


def test_importing_the_module_loads_no_label_module():
    code = ("import sys, efv_drivers; "
            "print(','.join(sorted(m for m in sys.modules "
            "if m.split('.')[0] in %r)))" % sorted(_LABEL_MODULES))
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", r.stdout


_WAR_TOKEN = re.compile(r"(^|[^a-z])(e|f|b)?war([^a-z]|$)")
_LABEL_WORDS = {"l6", "w2", "w3", "r3", "reached", "label", "labels"}


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


def test_source_names_no_war_or_label_column():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert not _WAR_TOKEN.search(low), name
        assert not set(low.split("_")) & _LABEL_WORDS, name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not _WAR_TOKEN.search(low), (node.value, node.lineno)
            assert not set(re.split(r"[^a-z0-9]+", low)) & _LABEL_WORDS, node.value


# ---------------------------------------------------------------------------
# synthetic universe (no disk, no cache)
# ---------------------------------------------------------------------------

_YEARS = range(2015, 2020)


def _synthetic(n=260, seed=7):
    """Records with one real-grader read per preseason 2015-2019 and a MiLB vector per
    vintage. The consensus moves by a function of the vector plus noise."""
    rng = random.Random(seed)
    recs, feats = {}, {}
    for i in range(n):
        pk = f"syn_{i:04d}"
        mid = 9_100_000 + i
        c = rng.gauss(44.0, 4.0)
        pts = []
        for y in _YEARS:
            x = {k: rng.gauss(0.0, 1.0) for k in DR.HIT_FEATURES}
            x.update(age=19.0 + (y - 2015) + rng.random(), rates_missing=0.0,
                     milb_season=y - 1)
            feats[(mid, y)] = x
            pts.append({"snapshot_date": f"{y}-02-01", "consensus_fv_raw": round(c, 2),
                        "sources_contributing": ["fangraphs"],
                        "per_source": {"fangraphs": {"fv_published": round(c),
                                                     "snapshot_date": f"{y}-02-01"}}})
            c += 0.8 * x["ops_rel"] - 0.05 * (c - 44.0) + rng.gauss(0.0, 1.0)
        recs[pk] = {"player_key": pk, "mlbam_id": mid, "debut_date": None,
                    "position": "SS", "birth_date": "1996-03-01", "points": pts,
                    "statline": {}}
    return recs, feats


@pytest.fixture
def synthetic(monkeypatch):
    recs, feats = _synthetic()

    def milb(mlbam, V, birth, side="hit", annotate=False, cutoff=None):
        return dict(feats[(int(mlbam), int(V))])

    monkeypatch.setattr(F.D, "_milb_features", milb)
    monkeypatch.setattr(F, "_mlb_ids", lambda season: frozenset())
    return recs


def _poisoned(recs):
    out = copy.deepcopy(recs)
    for r in out.values():
        r.update(war=1e9, ewar_6yr=-1e9, fwar=float("nan"), l6=5.0, w3=7.0,
                 reached="reached", label_6yr=3.0)
        r["statline"] = {"war": 99.0, "ewar": 99.0}
        for p in r["points"]:
            p["war"] = 1e9
            p["per_source"]["fangraphs"]["war"] = -1e9
    return out


def test_outputs_ignore_every_war_like_field(synthetic):
    clean = DR.consensus_revision_hat("hit", 2018, universe=synthetic)
    dirty = DR.consensus_revision_hat("hit", 2018, universe=_poisoned(synthetic))
    assert clean["status"] == "ok" and clean["hat"]
    assert clean["hat"] == dirty["hat"]
    assert clean["hat_base"] == dirty["hat_base"]
    assert clean["coef"] == dirty["coef"]


# ---------------------------------------------------------------------------
# 2. forward chaining
# ---------------------------------------------------------------------------

def _shift_year(recs, year, by):
    out = copy.deepcopy(recs)
    for r in out.values():
        for p in r["points"]:
            if p["snapshot_date"].startswith(str(year)):
                p["consensus_fv_raw"] = round(p["consensus_fv_raw"] + by, 2)
    return out


def test_prediction_for_v_uses_no_later_read(synthetic):
    V = 2017
    base = DR.consensus_revision_hat("hit", V, universe=synthetic)
    assert base["status"] == "ok"
    assert base["train_vintages"] and max(base["train_vintages"]) < V
    later = DR.consensus_revision_hat("hit", V, universe=_shift_year(synthetic, V + 1, 9.0))
    assert later["hat"] == base["hat"] and later["coef"] == base["coef"]
    # liveness: an earlier read does move the fit
    earlier = DR.consensus_revision_hat("hit", V, universe=_shift_year(synthetic, V - 1, 9.0))
    assert earlier["coef"] != base["coef"]


def test_front_runner_learns_a_planted_revision(synthetic):
    """The synthetic consensus moves with ops_rel; the full model must find it."""
    fit = DR.consensus_revision_hat("hit", 2019, universe=synthetic)
    assert fit["status"] == "ok"
    assert fit["coef"]["ops_rel"] > 0.3
    assert fit["n_train"] >= DR.MIN_TRAIN_ROWS


def test_targets_are_grade_differences(synthetic):
    tgt = DR.revision_targets("hit", 2016, universe=synthetic)
    r = synthetic["syn_0000"]
    c0 = r["points"][1]["consensus_fv_raw"]
    c1 = r["points"][2]["consensus_fv_raw"]
    assert tgt["syn_0000"] == pytest.approx(c1 - c0)


# ---------------------------------------------------------------------------
# 3. reserved guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_vintages_raise(V):
    with pytest.raises(F.ReservedFrameError):
        DR.consensus_revision_hat("hit", V, universe={})
    with pytest.raises(F.ReservedFrameError):
        DR.consensus_revision_hat("pit", V, universe={}, gate_sha="0" * 40)


def test_target_read_into_a_reserved_vintage_raises():
    # V = 2019 is development, but its target is the 2020 read.
    with pytest.raises(F.ReservedFrameError):
        DR.revision_targets("hit", 2019, universe={})


def test_dev_oos_refuses_non_development_vintages():
    for bad in ((2019, 2020), (2021,), (2025,), (2010, 2011)):
        with pytest.raises(F.ReservedFrameError):
            DR.dev_oos_r2("hit", bad, universe={})
    # the last development vintage has no development target, so it is skipped
    out = DR.dev_oos_r2("hit", (2019,), universe={})
    assert out["n_oos"] == 0 and out["per_vintage"] == {}


# ---------------------------------------------------------------------------
# 4. D3 as-of cutoff
# ---------------------------------------------------------------------------

def _tx(date, code, desc=""):
    return {"date": date, "type_code": code, "description": desc,
            "from_team_id": 1, "to_team_id": 2, "id": None}


_HIST = {"p": [
    _tx("2015-06-20", "ASG", "assigned to Low-A"),
    _tx("2016-11-18", "SE", "selected the contract"),
    _tx("2017-03-20", "OPT", "optioned"),
    _tx("2018-06-01", "OUT", "sent outright"),
    _tx("2019-11-20", "SE", "selected the contract"),
]}


def test_forty_man_respects_the_cutoff():
    f = DR.forty_man_asof("p", "2015-01-01", transactions=_HIST)
    assert f["observed"] is False and f["on_40man"] is None
    f = DR.forty_man_asof("p", "2016-11-18", transactions=_HIST)
    assert f["observed"] is True and f["on_40man"] is False and f["november_adds"] == []
    f = DR.forty_man_asof("p", "2016-11-19", transactions=_HIST)
    assert f["on_40man"] is True and f["november_adds"] == ["2016-11-18"]
    f = DR.forty_man_asof("p", "2018-06-01", transactions=_HIST)
    assert f["on_40man"] is True and f["status_event"] == "OPT"
    f = DR.forty_man_asof("p", "2018-06-02", transactions=_HIST)
    assert f["on_40man"] is False and f["status_event"] == "OUT"
    f = DR.forty_man_asof("p", "2020-01-01", transactions=_HIST)
    assert f["on_40man"] is True and f["november_adds"] == ["2016-11-18", "2019-11-20"]
    assert DR.forty_man_asof("nobody", "2020-01-01", transactions=_HIST)["on_40man"] is None


def test_contract_selections_respect_the_cutoff():
    assert DR.contract_selections_asof("p", "2016-11-18", transactions=_HIST) == []
    sel = DR.contract_selections_asof("p", "2019-11-21", transactions=_HIST)
    assert [s["date"] for s in sel] == ["2016-11-18", "2019-11-20"]
    assert all(s["november"] for s in sel)


@pytest.mark.skipif(not _HAVE_DATA, reason="served data files absent")
def test_real_org_signals_ignore_everything_after_the_window_start():
    rows = F.build_frame("hit", 2018, milb=False, sidecars=False)
    assert rows
    txs = DR.load_transactions()
    keys = {r["player_key"] for r in rows}
    cut = rows[0]["window"][0]
    truncated = {k: [t for t in (txs.get(k) or []) if DR._tx_date(t) < cut] for k in keys}
    full = DR.org_signals_for_frame(copy.deepcopy(rows), transactions=txs)
    trim = DR.org_signals_for_frame(copy.deepcopy(rows), transactions=truncated)
    cols = ("tx_observed", "forty_man_at_v", "november_added_before_v",
            "contract_selections_before_v", "rule5_selected_before_v")
    for a, b in zip(full, trim):
        assert a["tx_cutoff"] == cut
        assert {c: a[c] for c in cols} == {c: b[c] for c in cols}, a["player_key"]
        for s in DR.contract_selections_asof(a["player_key"], cut, transactions=txs):
            assert s["date"] < cut
    assert any(r["forty_man_at_v"] for r in full)


# ---------------------------------------------------------------------------
# 5. no FV-cell grouping
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


def test_no_fv_cell_grouping():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), node.value
