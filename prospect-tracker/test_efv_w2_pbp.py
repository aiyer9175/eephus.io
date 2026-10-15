# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the pitch-event discipline columns (efv_w2_pbp.py, EFV4_PBP_DISCIPLINE_ARMS).

1. Counting: call codes land in the declared counts; a game below the full-game rule
   gives nothing; bunts, intentional balls and automatic calls leave every count; the
   first pitch is the 0-0 pitch of a batter PA.
2. Population z and k_resid: a pool's mean and sd come from its qualifying lines; a thin
   pool gives no value; k_resid is z(K) minus the pool slope times z(swstr).
3. As of: the last two played seasons ending before the read (2020 skipped); a season
   at or after the read is never touched; shrinkage is D / (D + K).
4. Keys and bans: the outcome-blind id; reserved vintages raise; the arms are twelve
   skill-head columns registered in wave 2; the restricted frame still excludes every
   frame player of a fold from its training rows; no consensus-level grouping, no
   served exporter, no em-dash, no label read by a column builder.
5. The artifact, when present: development role, the frozen label, the family's floors
   before its arms, every spent block labelled, ledger rows for development frames only.
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
sys.path.insert(0, str(ROOT / "tools"))

import efv_screen_lab as LAB  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_pbp as M  # noqa: E402

SRC = ROOT / "efv_w2_pbp.py"
PCOLS = ["ab", "n", "code", "b0", "s0", "b1", "s1", "traj", "hard", "loc", "x", "y"]


def _p(ab, n, code, b0, s0):
    return [ab, n, code, b0, s0, None, None, None, None, None, None, None]


def _game(pas, pitches):
    return {"pa_cols": ["ab", "batter", "pitcher", "event", "inning", "top"],
            "pitch_cols": PCOLS, "pa": pas, "pitches": pitches}


# ---------------------------------------------------------------------------
# 1. counting
# ---------------------------------------------------------------------------

def test_codes_land_in_their_counts():
    pas = [[0, 1, 9, "strikeout", 1, 1], [1, 2, 9, "single", 1, 1],
           [2, 1, 9, "walk", 1, 1]]
    pitches = [_p(0, 1, "C", 0, 0), _p(0, 2, "F", 0, 1), _p(0, 3, "S", 0, 2),
               _p(1, 1, "S", 0, 0), _p(1, 2, "L", 0, 1), _p(1, 3, "B", 0, 1),
               _p(1, 4, "X", 1, 1),
               _p(2, 1, "I", 0, 0), _p(2, 2, "B", 1, 0), _p(2, 3, "*B", 2, 0),
               _p(2, 4, "B", 3, 0)]
    full, hit, pit = M.game_counts(_game(pas, pitches))
    assert full
    h1 = dict(zip(M.HIT_COUNTS, hit[1]))
    # batter 1: PA 0 (C, F, S at two strikes) and PA 2 (I not counted, then B, *B, B)
    assert h1 == {"pitches": 6, "swings": 2, "whiffs": 1, "pa": 2, "so": 1,
                  "fp_den": 1, "fp_called": 1, "two_swings": 1, "two_whiffs": 1}
    h2 = dict(zip(M.HIT_COUNTS, hit[2]))
    # batter 2: S, L (bunt, not counted), B, X
    assert h2 == {"pitches": 3, "swings": 2, "whiffs": 1, "pa": 1, "so": 0,
                  "fp_den": 1, "fp_called": 0, "two_swings": 0, "two_whiffs": 0}
    q = dict(zip(M.PIT_COUNTS, pit[9]))
    assert q == {"pitches": 9, "whiffs": 2, "called": 1, "balls": 4, "bf": 3, "so": 1,
                 "fp_den": 2, "fp_strike": 2}


def test_a_result_only_game_gives_nothing():
    pas = [[i, 1, 9, "field_out", 1, 1] for i in range(4)]
    pitches = [_p(i, 1, "X", 0, 0) for i in range(4)]
    full, hit, pit = M.game_counts(_game(pas, pitches))
    assert full is False and hit == {} and pit == {}


def test_runner_events_count_pitches_but_no_pa():
    pas = [[0, 1, 9, "caught_stealing_2b", 1, 1]]
    pitches = [_p(0, 1, "B", 0, 0), _p(0, 2, "S", 1, 0), _p(0, 3, "C", 1, 1)]
    full, hit, _pit = M.game_counts(_game(pas, pitches))
    h = dict(zip(M.HIT_COUNTS, hit[1]))
    assert full and h["pitches"] == 3 and h["pa"] == 0 and h["fp_den"] == 0


# ---------------------------------------------------------------------------
# 2. population z and k_resid
# ---------------------------------------------------------------------------

def _lines(n, *, so_step=1):
    out = {}
    for i in range(n):
        c = {k: 0 for k in M.HIT_COUNTS}
        c.update(pitches=400, swings=180, whiffs=20 + i, pa=110, so=10 + so_step * i,
                 fp_den=100, fp_called=30, two_swings=60, two_whiffs=10)
        out[1000 + i] = M._derived(c, "hit")
    return out


@pytest.fixture
def pool(monkeypatch):
    lines = _lines(40)
    monkeypatch.setattr(M, "pool_lines", lambda sp, y, side: lines if (sp, y) == (11, 2015)
                        and side == "hit" else {})
    M.pool_norm.cache_clear()
    yield lines
    M.pool_norm.cache_clear()


def test_pool_norm_and_line_z(pool):
    nm = M.pool_norm(11, 2015, "hit")
    xs = [(20 + i) / 400 for i in range(40)]
    m = sum(xs) / 40
    assert abs(nm["rates"]["swstr_h"]["mean"] - m) < 1e-12
    # K rises one-for-one with whiffs, so z(K) = z(swstr), slope 1, residual 0
    assert abs(nm["rates"]["k_resid_h"]["slope"] - 1.0) < 1e-9
    z = M.line_z(pool[1039], 11, 2015, "hit")
    assert z["swstr_h"] > 1.5 and abs(z["k_resid_h"]) < 1e-9


def test_a_thin_pool_gives_no_value(monkeypatch):
    lines = _lines(M.NORM_MIN_LINES - 1)
    monkeypatch.setattr(M, "pool_lines", lambda sp, y, side: lines)
    M.pool_norm.cache_clear()
    assert M.pool_norm(11, 2015, "hit") is None
    assert M.line_z(lines[1000], 11, 2015, "hit") == {}
    M.pool_norm.cache_clear()


# ---------------------------------------------------------------------------
# 3. as of and shrinkage
# ---------------------------------------------------------------------------

def test_read_seasons_are_the_last_two_played_before_the_read():
    assert M.read_seasons(2018, "2018-01-01") == [2017, 2016]
    assert M.read_seasons(2021, "2021-01-01") == [2019, 2018]
    assert M.read_seasons(2022, None) == [2021, 2019]
    # a cutoff before 1 October drops the season still being played
    assert M.read_seasons(2019, "2018-07-01") == [2017, 2016]


def test_the_live_read_seasons_are_aggregated():
    # EFV_FIX_A_PBP_2026 (audit D6): the live board reads list year 2026 at read year
    # 2027 as of an October cutoff, so it asks for 2026 and 2025; both are pools now.
    live = M.read_seasons(2027, "2026-10-15")
    assert live == [2026, 2025] and set(live) <= set(M.AGG_SEASONS)
    assert max(M.AGG_SEASONS) == 2026 and 2020 not in M.AGG_SEASONS


def test_complete_pools_take_the_new_seasons_only_when_complete():
    cells = [{"sportId": 11, "season": 2026, "fetch_planned": True, "complete": True},
             {"sportId": 12, "season": 2026, "fetch_planned": True, "complete": False},
             {"sportId": 16, "season": 2025, "fetch_planned": True, "complete": True},
             {"sportId": 16, "season": 2023, "fetch_planned": False, "complete": False},
             {"sportId": 11, "season": 2027, "fetch_planned": True, "complete": True}]
    assert M.complete_pools({"cache": {"cells": cells}}) == [(11, 2026), (16, 2025)]


def test_the_census_holds_every_live_pool_complete():
    if not M.CENSUS_PATH.exists():
        pytest.skip("pbp_census.json not built on this tree")
    doc = json.loads(M.CENSUS_PATH.read_text(encoding="utf-8"))
    planned = {(int(s), int(y)) for s, y in doc["probe"]["fetch_cells"] if int(y) >= 2025}
    cells = {(int(c["sportId"]), int(c["season"])): c for c in doc["cache"]["cells"]}
    assert {(11, 2026), (12, 2026), (13, 2026), (14, 2026)} <= planned
    for k in sorted(planned):
        c = cells[k]
        assert c["complete"] and c["games_cached"] >= c["scheduled_final"] > 0, k


def test_profile_reads_only_its_seasons_and_shrinks(monkeypatch):
    seen = []
    line = {"pa": 50}

    def fake_lines(sp, y, side):
        seen.append(y)
        return {7: line} if sp == 11 else {}

    monkeypatch.setattr(M, "pool_lines", fake_lines)
    monkeypatch.setattr(M, "line_z", lambda c, sp, y, side: {"swstr_h": 1.0})
    p = M.profile(7, 2018, "2018-01-01", "hit")
    assert set(seen) == {2017, 2016}
    d = 100.0
    assert abs(p["swstr_h"] - d / (d + M.SHRINK_K["swstr_h"])) < 1e-12
    assert p["contact_h"] is None and p["_exposure"] == d
    assert M.profile(None, 2018, None, "hit")["swstr_h"] is None


# ---------------------------------------------------------------------------
# 4. keys, arms, registration, bans
# ---------------------------------------------------------------------------

def test_lv_values_read_the_outcome_blind_id(monkeypatch):
    got = []
    monkeypatch.setattr(M, "profile", lambda pid, y, cut, side: got.append((pid, y, cut))
                        or {c: 0.5 for c in M.COLUMNS[side]})
    rows = [{"player_key": "x", "mlbam_id": 111, "record_mlbam_id": 222,
             "window": ["2018-01-01", "2018-05-01"]}]
    vals = M.lv_values("hit", {"hit": {2018: (rows, [{}])}})
    assert got == [(111, 2018, "2018-01-01")] and set(vals) == {(2018, "x")}


def test_reserved_list_vintages_raise():
    rows = [{"player_key": "x", "mlbam_id": 1, "window": ["2020-01-01", "2020-05-01"]}]
    with pytest.raises(F.ReservedFrameError):
        M.lv_values("hit", {"hit": {2020: (rows, [{}])}})


def test_vm_values_skip_the_reserved_cohort(monkeypatch):
    monkeypatch.setattr(M, "profile", lambda pid, y, cut, side: {"y": y})
    data = [{"player_key": "a", "decision_year": 2024},
            {"player_key": "b", "decision_year": F.R_VM_FIRST_DEBUT_YEAR}]
    raw = {"a": {"mlbam_id": 1, "cutoff": "2024-01-01"},
           "b": {"mlbam_id": 2, "cutoff": "2025-01-01"}}
    assert set(M.vm_values("hit", data, raw)) == {"a"}
    assert set(M.vm_values("hit", data, raw, allow_reserved=True)) == {"a", "b"}


def test_the_arms_are_twelve_skill_columns_registered_in_wave_two():
    names = [a["name"] for a in M.ARMS]
    assert len(names) == 12 == len(set(names))
    assert {a["head"] for a in M.ARMS} == {"skill"}
    assert [a["stat"] for a in M.ARMS if a["side"] == "hit"] == list(M.COLUMNS["hit"])
    assert [a["stat"] for a in M.ARMS if a["side"] == "pit"] == list(M.COLUMNS["pit"])
    for a in M.ARMS:
        assert a["column"] == {"source": "module", "module": "efv_w2_pbp",
                               "attr": "screen_column", "arg": a["stat"]}
        assert M.SHRINK_K[a["stat"]] > 0
    assert "efv_w2_pbp" in LAB.WAVE2_ARM_MODULES
    assert set(names) <= {a["name"] for a in LAB.wave2_candidates()}
    assert LAB.registration_echo()["family_size"] == 7
    with pytest.raises(ValueError):
        M.screen_column("pbp_absent", "hit", {})


def test_the_restricted_frame_keeps_every_fold_player_out_of_training():
    def row(pk, y):
        return {"player_key": pk, "decision_year": y, "fv": 45.0, "target": 0.0,
                "reached": 0.0, "v2": {}}
    train = {"hit": [row("a", 2015), row("b", 2015), row("c", 2016)], "pit": []}
    tests = {("hit", 2017): [row("a", 2017), row("d", 2017)], ("pit", 2017): []}
    scored = {("hit", 2017): [{"key": "a"}, {"key": "d"}], ("pit", 2017): []}
    full = LAB.Frame(train, tests, scored, weights={}, folds=(2017,))
    keep = {"hit": {(2015, "a"), (2015, "b"), (2016, "c"), (2017, "d")}, "pit": set()}
    sub = M.restricted_frame(full, keep)
    assert [r["player_key"] for r in sub.tests[("hit", 2017)]] == ["d"]
    # "a" is a 2017 frame player without a value there, so its 2015 row stays out
    assert [r["player_key"] for r in sub.fold_train("hit", 2017)] == ["b", "c"]
    assert sub.counts["hit"]["2017"]["test_rows_full"] == 2


def test_the_v3_registration_is_scoped_and_restored():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    with M.registered_v3_columns() as cols:
        for a in M.ARMS:
            assert cols[a["name"]]["side"] == a["side"] and cols[a["name"]]["head"] == "skill"
    assert V3.W2_COLUMNS == before


_BANNED_TOKENS = ("groupby", "tier", "bucket", "stratum", "strata", "by_fv", "fv_cell",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")
_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def test_no_consensus_level_grouping_no_exporter_no_emdash():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED_TOKENS), name
            assert not fv_group.search(low), name
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & _SERVED_EXPORTERS, mods
    assert chr(0x2014) not in src and chr(0x2013) not in src
    for fn in ("game_counts", "aggregate_pool", "pool_lines", "pool_norm", "line_z",
               "read_seasons", "profile", "lv_values", "vm_values", "screen_column"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        low = body.lower().replace("r_vm_first_debut_year", "")
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            assert banned not in low, (fn, banned)


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def _load():
    if not M.OUT_PATH.exists():
        pytest.skip("efv_w2_pbp.json not built on this tree")
    return json.loads(M.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_with_its_family():
    d = _load()
    assert d["role"] == "development" and d["exploratory"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["label"]["id"].startswith("fwar@2026-10-02")
    lv = d["lv_dev"]
    assert lv["frame"]["folds"] == [2017, 2018, 2019]
    for side, cov in lv["coverage"].items():
        assert not ({"2020", "2021"} & set(cov)), side
    prim = lv["primary"]
    assert list(prim).index("floors") < list(prim).index("arms")
    assert prim["holm"]["m"] == len(M.ARMS) == d["family"]["m"]
    for s in ("hit", "pit"):
        assert prim["floors"]["skill"][s]["n_noise"] == M.N_NOISE
    for a in M.ARMS:
        arm = prim["arms"][a["name"]]
        assert arm["verdict"] in LAB.VERDICTS
        assert arm["permutation_null"]["n"] == d["family"]["n_perm"]
        for fid, blk in (("lv", lv["full_frame"]["arms"][a["name"]]["frame"]),
                         ("vm", d["vm_dev"]["arms"][a["name"]]["frame"])):
            leg = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            assert leg["delta"] is not None and len(leg["ci95"]) == 2, fid
    assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in d["vm_dev"]["frame"]["fold_years"])
    assert all(p["mismatched_base_order"] == 0 for p in d["vm_dev"]["parity"].values())
    sp = d.get("spent")
    if sp:
        assert sp["label"] == M.SPENT_LABEL and sp["selects"] is False
        for a in sp["arms"].values():
            assert a["label"] == M.SPENT_LABEL
            assert set(a["frames"]) == {"lv_res", "vm_pros"}


def test_the_ledger_rows_are_this_modules_development_rows_only():
    d = _load()
    docs = M.ledger_docs(d)
    assert len(docs) == 2 * len(M.ARMS)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(M.MODEL_PREFIX)
        assert set(doc["frames"]) <= {"lv_dev", "vm_dev"}
