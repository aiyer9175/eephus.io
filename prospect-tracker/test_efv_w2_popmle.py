# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the eFV v4 population translation column (efv_w2_popmle.py,
EFV4_POPULATION_TRANSLATION).

1. As of: a read at year Y learns only from population seasons whose six-season label
   window closed by Y - 1; a line, or an fWAR season, after the read never moves a value;
   the frame row reads its last season ended by its read.
2. Exclusion: every player of the frame read at Y is left out of that year's fit, and so
   is every post-debut player-season.
3. Guards: reserved list vintages and the R-VM cohort raise without the committed sha.
4. Isolation: the label join and the artifact live under data/_labs; efv_identity and no
   served exporter reads them (AST); no consensus-level grouping; no em-dash.
5. The artifact, when present: development role on the frozen label, spent frames
   labelled and kept out of the ledger rows.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_vintage_frame as F  # noqa: E402
import efv_w2_popmle as P  # noqa: E402

SRC = ROOT / "efv_w2_popmle.py"
PID = 900001


def _hit(pid, season, level="A", age=21, **kw):
    sport = {"AAA": 11, "AA": 12, "A+": 13, "A": 14, "CPX": 16}[level]
    row = {"mlbam": pid, "season": season, "sport": sport, "league": "XX", "level": level,
           "age": age, "pa": 400, "ab": 350, "h": 90, "doubles": 18, "triples": 2, "hr": 10,
           "bb": 40, "so": 80, "hbp": 5, "sf": 5, "sb": 10}
    row.update(kw)
    return row


def _clear():
    for fn in (P.season_lines, P.norms, P.player_seasons, P._join):
        fn.cache_clear()


@pytest.fixture
def world(monkeypatch):
    """A synthetic population at level A, 2005 to 2016: 60 players a season whose OBP
    rises with their id and whose label follows it; one player of interest (PID)."""
    store: dict = {}
    by: dict = {}
    for season in range(2005, 2017):
        rows = []
        for i in range(60):
            pid = 100000 + season * 100 + i
            rows.append(_hit(pid, season, age=19 + i % 6, h=60 + i, bb=20 + i // 2))
            by[str(pid)] = {str(season + 2): round(i / 10.0, 3)}
        store[(14, season, "hitting")] = rows
    for season in (2012, 2013, 2014):
        store[(14, season, "hitting")].append(_hit(PID, season, h=110, bb=55))

    def fake(sport, season, group, fetch=True):
        return list(store.get((int(sport), int(season), group), []))
    monkeypatch.setattr(P.mh, "season_splits", fake)
    monkeypatch.setattr(P, "MIN_TRAIN_ROWS", 50)
    join = {"by_mlbam": by, "first_mlb_season": {}}
    _clear()
    yield store, join
    _clear()


# ---------------------------------------------------------------------------
# 1. as of
# ---------------------------------------------------------------------------

def test_train_seasons_close_the_label_window_before_the_read():
    assert P.train_seasons(2011) == []
    assert P.train_seasons(2012) == [2005]
    assert P.train_seasons(2017) == list(range(2005, 2011))
    for y in range(2011, 2027):
        for s in P.train_seasons(y):
            assert s + P.HORIZON <= y - 1


def test_a_line_or_a_war_season_after_the_read_never_moves_the_value(world):
    store, join = world
    tr = P.Translator({("lv", 2015): set()}, join=join)
    v0, s0 = tr.value("hit", "lv", PID, 2015, "2015-02-01", 2005)
    assert s0 == 2014 and v0 is not None
    # a 2015 line (after the read) and fWAR seasons from 2015 on
    store[(14, 2015, "hitting")].append(_hit(PID, 2015, h=200, bb=150))
    for k in join["by_mlbam"]:
        join["by_mlbam"][k]["2016"] = 99.0
    _clear()
    tr2 = P.Translator({("lv", 2015): set()}, join=join)
    v1, s1 = tr2.value("hit", "lv", PID, 2015, "2015-02-01", 2005)
    assert (v1, s1) == (v0, s0)


def test_the_row_reads_its_last_season_ended_by_the_read(world):
    _store, join = world
    tr = P.Translator({("lv", 2015): set(), ("vm", 2015): set()}, join=join)
    assert tr.value("hit", "lv", PID, 2015, "2015-02-01", 2005)[1] == 2014
    # a floor above every season the player played reads nothing
    assert tr.value("hit", "lv", PID, 2015, "2015-02-01", 2015) == (None, None)
    assert tr.value("hit", "lv", None, 2015, "2015-02-01", 2005) == (None, None)
    # a read year with no closed label window fits nothing
    tr2 = P.Translator({("lv", 2011): set()}, join=join)
    assert tr2.value("hit", "lv", 100000 + 2010 * 100 + 3, 2011, "2011-02-01", 2005)[0] is None


# ---------------------------------------------------------------------------
# 2. exclusion
# ---------------------------------------------------------------------------

def test_frame_players_and_post_debut_seasons_leave_the_fit(world):
    _store, join = world
    ex = frozenset({100000 + 2006 * 100 + i for i in range(10)})
    join["first_mlb_season"] = {str(100000 + 2007 * 100 + 1): 2007}
    X, y, rec = P.training_rows("hit", 2016, ex, join=join)
    assert rec["seasons"] == [2005, 2009]
    assert rec["left_out_frame_players"] == 10
    assert rec["left_out_post_debut"] == 1
    assert rec["rows"] == 5 * 60 - 10 - 1 == len(y) == X.shape[0]


def test_the_translator_refuses_a_read_year_with_no_exclusion_set(world):
    _store, join = world
    tr = P.Translator({}, join=join)
    with pytest.raises(KeyError):
        tr.model("lv", 2015, "hit")


# ---------------------------------------------------------------------------
# 3. guards
# ---------------------------------------------------------------------------

def test_reserved_reads_raise_without_the_committed_sha(world):
    _store, join = world
    tr = P.Translator({("lv", 2020): set(), ("vm", 2025): set()}, join=join)
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            tr.value("hit", "lv", PID, V, f"{V}-02-01", 2005)
    with pytest.raises(F.ReservedFrameError):
        tr.value("hit", "vm", PID, F.R_VM_FIRST_DEBUT_YEAR, None, 2005)
    with pytest.raises(F.ReservedFrameError):
        tr.model("vm", F.R_VM_FIRST_DEBUT_YEAR, "hit")


# ---------------------------------------------------------------------------
# 4. isolation and bans
# ---------------------------------------------------------------------------

_SERVED = ("efv_identity", "efv_export", "efv_v2_serve", "efv_score", "build_site",
           "proj_export", "export_trade_values", "efv_alerts", "run_monthly", "efv_model",
           "efv_dataset", "efv_labels", "war_source")


def _names(tree) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


def test_the_label_join_lives_under_labs_and_no_served_module_reads_it():
    labs = ROOT / "data" / "_labs"
    assert labs in P.POP_FWAR_PATH.parents and labs in P.OUT_PATH.parents
    for mod in _SERVED:
        path = ROOT / f"{mod}.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = _names(tree)
        assert "efv_w2_popmle" not in names, mod
        assert not any("pop_fwar" in n for n in names), mod


def test_no_served_exporter_import_no_consensus_level_grouping_no_emdash():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = ("groupby", "tier", "bucket", "cell", "stratum", "by_fv", "fv_band",
              "fv_bin", "by_consensus", "per_fv", "per_consensus")
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in banned), name
            assert not fv_group.search(low), name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & set(_SERVED[1:9]), mods
    assert chr(0x2014) not in src and chr(0x2013) not in src
    # the population features and the column builders read no grade
    for fn in ("line_counts", "season_lines", "norms", "player_seasons", "vector"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        for word in ("grade", "consensus", "fv", "war", "label"):
            assert word not in body.lower().replace("forward", ""), (fn, word)


def test_the_arms_are_two_skill_columns_and_their_twins():
    assert [a["side"] for a in P.ARMS] == ["hit", "pit"]
    assert all(a["head"] == "skill" and not a["twin"] for a in P.ARMS)
    assert all(t["twin"] for t in P.TWINS)
    assert P.GBM_PARAMS["early_stopping"] is False


def test_the_twin_keeps_the_marginal_inside_each_year_and_role():
    vals = {(2017, f"p{i}", kind): float(i) for i in range(30) for kind in ("train", "test")}
    vals[(2018, "q", "test")] = None
    tw = P.twin_values(vals)
    assert set(tw) == set(vals)
    for y, kind in ((2017, "train"), (2017, "test")):
        a = sorted(v for k, v in vals.items() if k[0] == y and k[2] == kind)
        b = sorted(v for k, v in tw.items() if k[0] == y and k[2] == kind)
        assert a == b
    assert tw == P.twin_values(vals)


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def _artifact():
    if not P.OUT_PATH.exists():
        pytest.skip("development read not run on this tree")
    return json.loads(P.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_on_the_frozen_label():
    d = _artifact()
    assert d["role"] == "development" and d["adjudicates"] is False and d["selects"] is False
    assert d["label"]["provider"] == "fwar"
    assert str(d["label"]["id"]).startswith("fwar@2026-10-02")
    assert d["lv_dev"]["window"] == [2017, 2019]
    assert d["vm_dev"]["window"][1] < F.R_VM_FIRST_DEBUT_YEAR
    for key, rec in d["population_fits"].items():
        kind, y, _side = key.split("|")
        assert not (kind == "lv" and int(y) in F.RESERVED_LV), key
        assert not (kind == "vm" and int(y) >= F.R_VM_FIRST_DEBUT_YEAR), key
        if rec.get("seasons"):
            assert rec["seasons"][1] + P.HORIZON <= int(y) - 1, key
    for a in P.ARMS:
        for fid in ("lv_dev", "vm_dev"):
            leg = d[fid]["arms"][a["name"]]["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            assert leg["delta"] is not None and len(leg["ci95"]) == 2


def test_spent_frames_are_labelled_and_never_ledger_rows():
    d = _artifact()
    docs = P.ledger_docs(d)
    assert len(docs) == 2 * len(P.ARMS)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(P.MODEL_PREFIX)
        assert set(doc["frames"]) <= {"lv_dev", "vm_dev"}
    sp = d.get("spent")
    if sp:
        assert sp["note"] == P.SPENT_NOTE and sp["ledger_rows"] is False
        for fid in ("lv_res", "vm_pros"):
            assert sp[fid]["role"] == "spent" and sp[fid]["note"] == P.SPENT_NOTE

# ---------------------------------------------------------------------------
# 6. the population repairs (EFV_FIX_A, docs/efv-v2/EFV_FIX_A.md)
# ---------------------------------------------------------------------------

def test_the_repair_is_dark_until_the_refit():
    """The production heads refit on every export and this column moves their slopes, so
    the repair reaches the board only with EFV_FIX_B_REFIT's registered re-fit."""
    assert P.POP_REPAIR_ON is False
    assert P.NON_AFFILIATED_LEAGUES == frozenset({(11, "MEX")})


def test_count_columns_name_a_shared_denominator_once():
    assert P.count_columns("hit").count("pa") == 1
    assert P.count_columns("pit").count("bf") == 1
    for side in ("hit", "pit"):
        want = {c for pair in P.RATES[side].values() for c in pair}
        assert set(P.count_columns(side)) == want


def test_norms_sum_each_count_once_under_the_repair(world, monkeypatch):
    store, _join = world
    rows = store[(14, 2010, "hitting")]
    so = sum(r["so"] for r in rows)
    pa = sum(r["pa"] for r in rows)
    bb = sum(r["bb"] for r in rows)
    legacy = P.norms(2010, "hit")["lv"]["A"]
    assert abs(legacy["k"] - so / (4 * pa)) < 1e-12, "the legacy loop, kept while dark"
    monkeypatch.setattr(P, "POP_REPAIR_ON", True)
    _clear()
    fixed = P.norms(2010, "hit")["lv"]["A"]
    assert abs(fixed["k"] - so / pa) < 1e-12
    assert abs(fixed["bb"] - bb / pa) < 1e-12
    # every hitter's k_rel is now relative to the true pooled rate: the PA-weighted mean is 0
    ps = P.player_seasons(2010, "hit")
    num = sum(f["k_rel"] * f["exp"] for f in ps.values())
    assert abs(num / sum(f["exp"] for f in ps.values())) < 1e-12


def test_non_affiliated_lines_leave_the_population_under_the_repair(world, monkeypatch):
    store, _join = world
    store[(11, 2010, "hitting")] = [
        _hit(950000 + i, 2010, level="AAA", league="MEX", age=30) for i in range(25)]
    store[(11, 2010, "hitting")].append(_hit(960000, 2010, level="AAA", league="PCL"))
    _clear()
    assert sum(1 for t in P.season_lines(2010, "hit") if t[2] == "MEX") == 25
    monkeypatch.setattr(P, "POP_REPAIR_ON", True)
    _clear()
    lines = P.season_lines(2010, "hit")
    assert not any(t[2] == "MEX" for t in lines)
    assert any(t[0] == 960000 for t in lines)
    assert ("AAA", "MEX") not in P.norms(2010, "hit")["lg"]
    assert 950000 not in P.player_seasons(2010, "hit")


@pytest.fixture
def repaired_cache(monkeypatch):
    """The real MiLB cache under the repair (skipped where the cache is absent)."""
    if not P.mh.season_splits(11, 2026, "hitting", fetch=False):
        pytest.skip("no 2026 AAA hitting cache on this tree")
    monkeypatch.setattr(P, "POP_REPAIR_ON", True)
    _clear()
    yield
    _clear()


def test_a_real_season_reads_league_rates_at_their_true_size(repaired_cache):
    """2026 AAA hitters struck out in about 22% of plate appearances; the legacy loop read
    0.056 (a quarter)."""
    nm = P.norms(2026, "hit")["lv"]["AAA"]
    assert 0.20 < nm["k"] < 0.25
    assert 0.20 < P.norms(2026, "pit")["lv"]["AAA"]["k"] < 0.25


@pytest.mark.parametrize("season", [2015, 2026])
def test_every_rate_is_league_relative_over_the_population(repaired_cache, season):
    """Over every line of a season, the denominator-weighted mean of (rate - its reference)
    is near 0 for every rate of both sides, and the exposure-weighted population mean of
    each *_rel whose denominator is the exposure is near 0."""
    for side in ("hit", "pit"):
        nm = P.norms(season, side)
        for r, (num, den) in P.RATES[side].items():
            x = w = xr = 0.0
            for _pid, lv, lg, _age, c in P.season_lines(season, side):
                ref = P._norm_rate(nm, lv, lg, r)
                if c[den] <= 0 or ref is None:
                    continue
                x += (c[num] / c[den] - ref) * c[den]
                w += c[den]
                xr += ref * c[den]
            assert abs(x / w) < 1e-6 * (xr / w), (side, r, x / w)
        exp_den = {"hit": "pa", "pit": "bf"}[side]
        ps = P.player_seasons(season, side)
        for r, (_num, den) in P.RATES[side].items():
            if den != exp_den:
                continue
            vals = [(f[f"{r}_rel"], f["exp"]) for f in ps.values() if f[f"{r}_rel"] == f[f"{r}_rel"]]
            mean = sum(v * e for v, e in vals) / sum(e for _v, e in vals)
            assert abs(mean) < 1e-6, (side, r, mean)
