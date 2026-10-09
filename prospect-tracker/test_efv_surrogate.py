# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_3 pins (docs/efv-v2/SURROGATE_2026_GATE.md s3 and s4): the surrogate outcome builder
efv_surrogate.py.

1. Constants: the exposure floor, the rungs, the penalty grid, the fit vintages.
2. Hygiene: no label, source-scorer or AP+ import; the R-LV score guard is never named;
   sport-1 lines are read for their id and nothing else; nothing is written.
3. Every public entry point refuses until the surrogate gate is REGISTERED, asks the
   guard before it reads anything, and refuses R-LV; a 2026 read needs the ETA record;
   an in-window R-VM debut refuses the whole read (never dropped).
4. The private pure functions on synthetic rows: the primary rung, the two level
   conventions, rung_pre and age_pre, S1 to S5, the as-of org, the residual maps, the
   club table, the components, the S_idx ridge and its two fold schemes, g_S.
5. The Mexican League on the 2016 and 2019 files (349 of 1,627 and 336 of 1,665 hitter
   lines) is dropped from S1, S4 and the norms.
6. The V-1 derivation reproduces the frame's level_rank on every V 2015-2019 row that
   carries one inside the pinned store.
7. A league-wide shape test on the 2015-2019 season files: S1 and raw S2 for every
   player in the file, counts per rung only. No association with any score or label.

Every row the fitters see here is synthetic; no label, score or rater column is read and
no 2026 outcome is computed.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

import efv_surrogate as S
import efv_surrogate_guard as G
import milb_history as mh
from efv_vintage_frame import ReservedFrameError
from tools import milb_season_freeze as Z

ROOT = Path(__file__).parent
SRC = (ROOT / "efv_surrogate.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
HAS_CACHE = (mh.CACHE_DIR / "hitting_11_2015.json").exists()
needs_cache = pytest.mark.skipif(not HAS_CACHE, reason="no .cache/milb_stats on this box")


@pytest.fixture(autouse=True)
def _never_fetch(monkeypatch):
    def boom(url):
        raise AssertionError(f"a surrogate test tried to fetch {url}")
    monkeypatch.setattr(mh, "_fetch", boom)


@pytest.fixture()
def fresh_store(monkeypatch):
    """Empty memos, so a test sees the store read path from the start."""
    for name in ("_CHECKED", "_INDEX", "_EVENTS", "_NORMS", "_AGES", "_FULL"):
        monkeypatch.setattr(S, name, type(getattr(S, name))())


# ---------------------------------------------------------------------------
# 1. constants
# ---------------------------------------------------------------------------

def test_constants():
    assert S.EXPOSURE_FLOOR == {"hit": 50.0, "pit": 60.0}
    assert S.RUNG == {"DSL": 0.0, "CPX": 1.0, "SSA": 1.5, "A": 2.0, "A+": 3.0,
                      "AA": 4.0, "AAA": 5.0}
    assert S.MLB_RUNG == 6.0
    assert S.FIT_VINTAGES == (2011, 2012, 2013, 2014, 2015, 2016)
    assert set(S.FALLBACK_VINTAGES) <= set(S.FIT_VINTAGES)
    assert S.G_S_VINTAGES == tuple(range(2011, 2020))
    assert S.FOLD_SEED == 20260930 and S.N_FOLDS == 5
    assert len(S.CLUBS) == 30


#: git blob of efv_surrogate.py at its first commit (SG_3): the module is new, so the
#: pin names the reviewed text; a later edit re-pins it in its own commit.
BUILDER_BLOB = "2853ba7c8e17a4ced1ccdb93959db34cf42f2e0c"


def test_the_builder_blob_is_pinned():
    import subprocess
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD:./efv_surrogate.py"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("efv_surrogate.py is not committed at HEAD")
    assert r.stdout.strip() == BUILDER_BLOB


def test_the_grid_is_the_finite_v2_grid():
    import efv_v2_model as M
    assert S.RIDGE_GRID == tuple(a for a in M.V2_ALPHAS if math.isfinite(a))


def test_placeholder_orgs_match_the_identity_audit():
    import identity_audit
    assert S.PLACEHOLDER_ORGS == identity_audit.PLACEHOLDER_ORGS


def test_no_pre_v_input_and_no_rater_input_in_the_fitters():
    banned = {"rung_pre", "age_pre", "level_rank", "age_rel_level", "pre_absent",
              "consensus", "fv", "grades", "pick_overall", "bonus_usd", "on_40man"}
    for side in S.SIDES:
        assert not set(S.FEATURES[side]) & banned
        assert "absent" in S.FEATURES[side]
    assert "s4_gs" in S.FEATURES["pit"] and "s4_gs" not in S.FEATURES["hit"]


# ---------------------------------------------------------------------------
# 2. hygiene
# ---------------------------------------------------------------------------

def _imports() -> set[str]:
    out = set()
    for n in ast.walk(TREE):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            out.add((n.module or "").split(".")[0])
    return out


def test_no_label_scorer_or_ap_plus_import():
    banned = {"efv_labels", "source_backtest", "advancement_pace_export",
              "advancement_pace", "efv_model", "war_source", "ewar", "efv_v2_stat"}
    assert not _imports() & banned


def test_the_r_lv_score_guard_is_never_named():
    assert "guard_score_request" not in SRC


def test_no_served_norm_blend_is_read():
    names = {n.attr for n in ast.walk(TREE) if isinstance(n, ast.Attribute)}
    assert "league_norms" not in names
    assert "_resolved_norms" not in names
    assert "level_norms_from_rows" in names


def test_nothing_is_written():
    for n in ast.walk(TREE):
        if isinstance(n, ast.Attribute):
            assert n.attr not in {"write_text", "write_bytes", "dump", "mkdir",
                                  "unlink", "replace", "rename"}, n.attr
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "open":
            raise AssertionError("efv_surrogate opens a file directly")
    for n in ast.walk(TREE):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            assert n.value not in {"w", "wb", "wt", "a", "ab"}, n.value


class _IdOnly(dict):
    """A sport-1 line that refuses every key but the person id."""

    def __getitem__(self, k):
        assert k == "mlbam", f"a sport-1 stat column was read: {k}"
        return dict.__getitem__(self, k)

    def get(self, k, default=None):
        assert k == "mlbam", f"a sport-1 stat column was read: {k}"
        return dict.get(self, k, default)


@needs_cache
def test_sport_one_lines_are_read_for_their_id_only(fresh_store, monkeypatch):
    real = Z.read_cache
    seen = []

    def wrapped(sport, season, group):
        rows = real(sport, season, group)
        if sport == 1:
            seen.append((season, group))
            return [_IdOnly(r) for r in rows]
        return rows
    monkeypatch.setattr(Z, "read_cache", wrapped)
    tj = S._tj_index()
    idx = S._season_index(2016, "hitting")
    ids = S._mlb_event_ids(2016, "hitting")
    assert ids and all(isinstance(i, int) for i in ids)
    pid = sorted(idx)[0]
    S._season_outcome(pid, 2016, "hit", tj, 2.0)
    assert (2016, "hitting") in seen


def test_the_store_refuses_a_drifted_pin(fresh_store, monkeypatch):
    if not HAS_CACHE:
        pytest.skip("no cache")
    doc = json.loads((S.DATA_DIR / S.PINS_NAME).read_text(encoding="utf-8"))
    doc["transfer_seasons"]["2015"]["hitting"]["12"]["sha256"] = "0" * 64
    monkeypatch.setattr(S, "_pins", lambda: doc)
    with pytest.raises(S.StoreError):
        S._season_lines(2015, "hitting")


def test_the_store_has_no_season_outside_its_pins(fresh_store):
    for s in (2009, 2027):
        with pytest.raises(S.StoreError):
            S._season_lines(s, "hitting")
    assert S._season_lines(2020, "hitting") == []
    with pytest.raises(S.StoreError):
        S._mlb_event_ids(2020, "hitting")


def test_a_2026_read_needs_the_eta_record_first(fresh_store, monkeypatch, tmp_path):
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)          # no eta_eval.json here
    monkeypatch.setattr(S, "_pins", lambda: (_ for _ in ()).throw(
        AssertionError("pins read before the ETA check")))
    with pytest.raises(ReservedFrameError):
        S._season_lines(2026, "hitting")
    with pytest.raises(ReservedFrameError):
        S._mlb_event_ids(2026, "pitching")
    with pytest.raises(ReservedFrameError):
        S._pure_norms(2026, "AA", "hitting")


def test_a_2026_file_off_its_pin_is_refused(fresh_store, monkeypatch, tmp_path):
    (tmp_path / G.ETA_EVAL_NAME).write_text(
        json.dumps({G.ETA_LOOK_BLOCK: {"decision": {"verdict": "fixture"}}}),
        encoding="utf-8")
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)
    monkeypatch.setattr(S, "_pins", lambda: {"frozen_2026": {"hitting_11.json":
                                                             {"sha256": "0" * 64}}})
    with pytest.raises(S.StoreError):
        S._check_2026("hitting_11.json", "frozen_2026")


# ---------------------------------------------------------------------------
# 3. public entry points
# ---------------------------------------------------------------------------

PUBLIC = sorted(n.name for n in TREE.body
                if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"))


def _frame_row(key="p1", V=2015, side="hit", person=1, debut=None):
    return {"player_key": key, "side": side, "vintage": V, "mlbam_id": person,
            "window": [f"{V}-01-01", f"{V}-05-01"], "debut_date": debut}


def _call(name, V=2015, purpose="transfer", **kw):
    fn = getattr(S, name)
    rows = [_frame_row(V=V)]
    if name == "mlb_event_ids":
        return fn(V, "hitting", purpose=purpose, **kw)
    if name == "build_outcomes":
        return fn("hit", V, rows, purpose=purpose, universe={}, tx={}, tj={}, **kw)
    if name in ("fit_maps", "fit_s_idx", "fit_g_s"):
        return fn(rows, "hit", purpose=purpose, **kw)
    if name == "apply_maps":
        return fn(rows, {"side": "hit"}, purpose=purpose, **kw)
    if name == "s_idx_scores":
        return fn({"features": S.FEATURES["hit"]}, rows, purpose=purpose, **kw)
    raise AssertionError(f"a public function the test does not know: {name}")


def test_the_public_surface_is_known():
    assert PUBLIC == ["apply_maps", "build_outcomes", "fit_g_s", "fit_maps",
                      "fit_s_idx", "mlb_event_ids", "s_idx_scores"]


@pytest.mark.parametrize("name", PUBLIC)
def test_every_public_function_refuses_until_registered(name, fresh_store, monkeypatch):
    monkeypatch.setattr(S, "_season_index", lambda *a: (_ for _ in ()).throw(
        AssertionError("the store was read before the guard")))
    with pytest.raises(ReservedFrameError):
        _call(name)
    with pytest.raises(ReservedFrameError):
        _call(name, gate_sha="0" * 40)


@pytest.mark.parametrize("name", PUBLIC)
@pytest.mark.parametrize("V", [2020, 2021])
def test_every_public_function_refuses_r_lv_for_every_purpose(name, V, monkeypatch):
    called = []
    monkeypatch.setattr(G, "gate_sha_committed_for", lambda *a: called.append(a) or True)
    for purpose in G.PURPOSES:
        with pytest.raises(ReservedFrameError):
            _call(name, V=V, purpose=purpose, gate_sha="f" * 40)
    assert not called, "a sha was checked before R-LV refused"


@pytest.mark.parametrize("name", PUBLIC)
def test_every_public_function_asks_the_guard_first(name, monkeypatch):
    class Asked(Exception):
        pass
    asked = []

    def guard(v, **kw):
        asked.append((v, kw.get("purpose")))
        raise Asked()
    monkeypatch.setattr(G, "guard_surrogate_read", guard)
    monkeypatch.setattr(S, "_season_index", lambda *a: (_ for _ in ()).throw(
        AssertionError("the store was read before the guard")))
    with pytest.raises(Asked):
        _call(name)
    assert asked == [(2015, "transfer")]


def test_an_in_window_r_vm_debut_refuses_the_whole_read(monkeypatch):
    monkeypatch.setattr(G, "guard_surrogate_read", lambda *a, **k: None)
    monkeypatch.setattr(S, "_season_index", lambda *a: (_ for _ in ()).throw(
        AssertionError("the store was read before the withhold")))
    rows = [_frame_row("a", V=2022, person=1),
            _frame_row("b", V=2022, person=2, debut="2025-06-01")]
    with pytest.raises(ReservedFrameError, match="2025: 1"):
        S.build_outcomes("hit", 2022, rows, purpose="transfer", universe={}, tx={}, tj={})


def test_fitters_refuse_rows_outside_their_vintages(monkeypatch):
    monkeypatch.setattr(G, "guard_surrogate_read", lambda *a, **k: None)
    with pytest.raises(ValueError):
        S.fit_maps([_frame_row(V=2017)], "hit", purpose="transfer")
    with pytest.raises(ValueError):
        S.fit_maps([_frame_row(V=2014)], "hit", purpose="transfer", fallback=True)
    with pytest.raises(ValueError):
        S.fit_s_idx([_frame_row(V=2018)], "hit", purpose="transfer")
    with pytest.raises(ValueError):
        S.fit_g_s([_frame_row(V=2022)], "hit", purpose="transfer")


def test_build_outcomes_refuses_a_row_of_another_frame(monkeypatch):
    monkeypatch.setattr(G, "guard_surrogate_read", lambda *a, **k: None)
    with pytest.raises(ValueError):
        S.build_outcomes("hit", 2015, [_frame_row(V=2016)], purpose="transfer",
                         universe={}, tx={}, tj={})
    with pytest.raises(ValueError):
        S.build_outcomes("pit", 2015, [_frame_row(side="hit")], purpose="transfer",
                         universe={}, tx={}, tj={})


# ---------------------------------------------------------------------------
# 4. the pure functions on synthetic rows
# ---------------------------------------------------------------------------

def _ln(pid, sport, level, pa=0, bf=0, league="", age=None, **extra):
    row = {"mlbam": pid, "level": level, "league": league, "pa": pa, "bf": bf,
           "age": age, **extra}
    return {"id": pid, "sport": sport, "league": league, "level": level, "row": row}


def test_primary_level_walks_down_to_the_first_level_at_the_floor():
    lines = [_ln(1, 12, "AA", pa=30), _ln(1, 13, "A+", pa=50), _ln(1, 14, "A", pa=300)]
    assert S._primary_level(lines, "hit", 2016)[0] == "A+"


def test_primary_level_falls_back_to_the_most_exposed_level():
    lines = [_ln(1, 12, "AA", pa=40), _ln(1, 13, "A+", pa=45), _ln(1, 14, "A", pa=10)]
    assert S._primary_level(lines, "hit", 2016)[0] == "A+"
    tie = [_ln(1, 12, "AA", pa=40), _ln(1, 13, "A+", pa=40)]
    assert S._primary_level(tie, "hit", 2016)[0] == "AA"


def test_primary_level_reads_the_largest_single_line_not_the_sum():
    lines = [_ln(1, 13, "A+", pa=30), _ln(1, 13, "A+", pa=30), _ln(1, 14, "A", pa=200)]
    assert S._primary_level(lines, "hit", 2016)[0] == "A"
    pit = [_ln(1, 12, "AA", bf=59), _ln(1, 13, "A+", bf=60)]
    assert S._primary_level(pit, "pit", 2016)[0] == "A+"


def test_the_two_level_conventions():
    mex = _ln(1, 11, "AAA", pa=400, league="MEX")
    ssa = _ln(1, 15, "A", pa=250, league="NYP")
    assert S._line_level(mex, 2016, "gate") is None
    assert S._line_level(mex, 2016, "efv_dataset") == "AAA"
    assert S._line_level(ssa, 2016, "gate") == "SSA"
    assert S._line_level(ssa, 2016, "efv_dataset") == "A"
    assert S._line_level(_ln(1, 11, "AAA", league="MEX"), 2021, "gate") == "AAA"
    assert S._primary_level([mex], "hit", 2016)[0] is None
    assert S._primary_level([mex, ssa], "hit", 2016)[0] == "SSA"
    assert S._primary_level([mex, ssa], "hit", 2016, "efv_dataset")[0] == "AAA"
    with pytest.raises(ValueError):
        S._line_level(ssa, 2016, "other")


@pytest.fixture()
def synthetic_store(monkeypatch):
    """A three-season synthetic store: person 1 at A in 2014 and A+ in 2015; person 2
    only at CPX in 2012; person 3 nowhere."""
    store = {
        (2012, "hitting"): {2: [_ln(2, 16, "CPX", pa=120, age=19)]},
        (2014, "hitting"): {1: [_ln(1, 14, "A", pa=400, age=20)]},
        (2015, "hitting"): {1: [_ln(1, 13, "A+", pa=450, age=21)]},
    }
    monkeypatch.setattr(S, "_season_index", lambda s, g: store.get((int(s), g), {}))
    return store


def test_rung_pre_reads_season_v_minus_1(synthetic_store):
    pre = S._pre_rung(1, 2016, "hit")
    assert (pre["rung_pre"], pre["rung_pre_season"], pre["pre_absent"]) == (3.0, 2015, False)
    assert pre["rung_pre_age"] == 21.0


def test_rung_pre_falls_back_to_the_latest_earlier_season(synthetic_store):
    pre = S._pre_rung(1, 2017, "hit")
    assert (pre["rung_pre"], pre["rung_pre_season"]) == (3.0, 2015)
    pre = S._pre_rung(2, 2016, "hit")
    assert (pre["rung_pre_level"], pre["rung_pre_season"]) == ("CPX", 2012)


def test_rung_pre_is_absent_without_a_line_or_an_id(synthetic_store):
    assert S._pre_rung(3, 2016, "hit")["pre_absent"] is True
    assert S._pre_rung(None, 2016, "hit")["pre_absent"] is True


def test_age_pre_is_age_at_v_minus_1_minus_the_qualifier_median(monkeypatch):
    med = {(2015, "A+"): 22.0, (2016, "CPX"): None, (2012, "CPX"): 20.0}
    monkeypatch.setattr(S, "_median_qualifier_age", lambda s, lv, side: med.get((s, lv)))
    pre = {"pre_absent": False, "rung_pre_season": 2015, "rung_pre_level": "A+",
           "rung_pre_age": 21.0}
    assert S._age_pre(pre, 2016, "hit") == -1.0
    stale = {"pre_absent": False, "rung_pre_season": 2012, "rung_pre_level": "CPX",
             "rung_pre_age": 19.0}
    assert S._age_pre(stale, 2017, "hit") == -1.0
    assert S._age_pre({"pre_absent": True}, 2016, "hit") is None


def test_qualifier_ages_take_each_player_s_largest_line_at_the_floor():
    lines = [_ln(1, 13, "A+", pa=40, age=20), _ln(1, 13, "A+", pa=60, age=20),
             _ln(2, 13, "A+", pa=49, age=25), _ln(3, 13, "A+", pa=300, age=22),
             _ln(4, 11, "AAA", pa=300, age=30, league="MEX")]
    assert sorted(S._qualifier_ages(lines, "A+", 2016, "hit")) == [20.0, 22.0]
    assert S._qualifier_ages(lines, "AAA", 2016, "hit") == []


def test_season_outcome_codes(monkeypatch):
    store = {1: [_ln(1, 12, "AA", pa=300, age=22, ab=270, h=80, so=60, bb=25,
                     slg=".450", avg=".296", obp=".360", ops=".810")],
             4: [_ln(4, 12, "AA", pa=300, age=22)]}
    monkeypatch.setattr(S, "_season_index", lambda s, g: store)
    monkeypatch.setattr(S, "_mlb_event_ids", lambda s, g: frozenset({4}))
    monkeypatch.setattr(S, "_full_season_exposure", lambda s, lv, side: 400.0)
    monkeypatch.setattr(S, "_pure_norms", lambda s, lv, g: {
        "obp": 0.330, "k_pct": 0.22, "bb_pct": 0.085, "iso": 0.135})
    tj = {2: ["2015-08-01"], 3: ["2016-10-15"]}
    a = S._season_outcome(1, 2016, "hit", tj, 3.0)
    assert (a["level_end"], a["climb_raw"], a["s5_status"]) == (4.0, 1.0, S.ACTIVE)
    assert a["pt_raw"] == 0.75 and set(a["perf_raw"]) == set(S.HIT_PERF)
    assert a["perf_raw"]["contact"] > 0          # a 20 percent K line against 22
    m = S._season_outcome(4, 2016, "hit", tj, 4.0)
    assert (m["level_end"], m["mlb_event"], m["perf_raw"]) == (6.0, True, None)
    assert m["climb_raw"] == 2.0
    assert S._season_outcome(2, 2016, "hit", tj, 2.0)["s5_status"] == S.ABSENT_KNOWN
    k = S._season_outcome(3, 2016, "hit", tj, 2.0)
    assert (k["s5_status"], k["level_end"], k["climb_raw"]) == (S.ABSENT_UNKNOWN, None, None)
    assert k["pt_raw"] == 0.0
    i = S._season_outcome(None, 2016, "hit", tj, 2.0)
    assert i["s5_status"] == S.ABSENT_IDENTITY and i["pt_raw"] is None


def test_the_tj_window():
    assert S._tj_explains(["2015-01-01"], 2016)
    assert S._tj_explains(["2016-09-30"], 2016)
    assert not S._tj_explains(["2014-12-31"], 2016)
    assert not S._tj_explains(["2016-10-01"], 2016)
    assert not S._tj_explains(None, 2016)


def test_playing_time_is_capped_and_drops_the_mexican_league():
    lines = [_ln(1, 12, "AA", bf=300, g=20, gs=15), _ln(1, 13, "A+", bf=300, g=10, gs=0),
             _ln(1, 11, "AAA", bf=500, g=30, gs=30, league="MEX")]
    full = {"AA": 600.0, "A+": 600.0, "AAA": 600.0}
    pt = S._playing_time(lines, 2016, "pit", full)
    assert pt == {"pt": 1.0, "gs_share": 0.5}
    pt = S._playing_time(lines[:1], 2016, "pit", full)
    assert pt == {"pt": 0.5, "gs_share": 0.75}
    assert S._playing_time([], 2016, "hit", full) == {"pt": 0.0}


def _pt(day, org):
    return {"snapshot_date": day, "org": org}


def test_asof_org_routes():
    win = ["2016-01-01", "2016-05-01"]
    tx = {7: [("2014-06-01", "BOS"), ("2015-12-20", "NYY"), ("2016-02-01", "SEA")]}
    pts = [_pt("2016-02-01", "Boston Red Sox"), _pt("2016-03-15", "New York Yankees"),
           _pt("2016-06-01", "Seattle Mariners")]
    assert S._asof_org(pts, win, 7, 2016, tx) == ("NYY", "board", "2016-03-15")
    pts = [_pt("2016-03-15", "Office of the Commissioner")]
    assert S._asof_org(pts, win, 7, 2016, tx) == ("NYY", "transactions", "2015-12-20")
    assert S._asof_org([_pt("2016-03-15", None)], win, 8, 2016, tx) == \
        (S.ORG_UNKNOWN, "unknown", None)
    assert S._asof_org([_pt("2016-06-01", "Seattle Mariners")], win, None, 2016, tx) == \
        (S.ORG_UNKNOWN, "unknown", None)
    early = ["2016-01-01", "2016-01-10"]           # an April-debut window cut short
    assert S._asof_org([_pt("2016-01-10", "Seattle Mariners")], early, 7, 2016, tx)[0] \
        == "NYY"


def test_tx_clubs_reads_the_destination_club(tmp_path):
    import gzip
    doc = {"transactions": [
        {"person": {"id": 7}, "date": "2015-03-01", "toTeam": {"id": 431, "name": "Gwinnett Braves"}},
        {"person": {"id": 7}, "date": "2015-04-01", "toTeam": {"name": "Somerset Patriots"}},
        {"person": {"id": 8}, "date": "2015-05-01", "toTeam": {"id": 147, "name": "New York Yankees"}},
    ]}
    with gzip.open(tmp_path / "tx_2015_03.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(doc, fh)
    out = S._tx_clubs(2015, tmp_path)
    assert out[7] == [("2015-03-01", "ATL")]
    assert out[8] == [("2015-05-01", "NYY")]


def test_residual_map_recovers_rung_intercepts_and_the_age_slope():
    rungs = [2.0] * 4 + [3.0] * 4
    ages = [-1.0, 0.0, 1.0, 2.0] * 2
    vals = [(0.5 if r == 2.0 else -0.25) + 0.3 * a for r, a in zip(rungs, ages)]
    m = S._fit_residual_map(vals, rungs, ages)
    assert m["by_rung"] == pytest.approx({2.0: 0.5, 3.0: -0.25})
    assert m["age_slope"] == pytest.approx(0.3)
    assert S._apply_residual_map(m, 1.0, 2.0, 1.0) == pytest.approx(0.2)
    assert S._apply_residual_map(m, 1.0, 5.0, 0.0) == pytest.approx(1.0 - m["pooled"])
    assert S._apply_residual_map(m, None, 2.0, 0.0) is None
    with pytest.raises(ValueError):
        S._fit_residual_map([], [], [])


def test_club_table_shrinks_toward_the_pooled_mean():
    rng = np.random.default_rng(1)
    clubs, vals = [], []
    for c, mu in (("BOS", 1.0), ("NYY", -1.0), ("SEA", 0.0)):
        for _ in range(30):
            clubs.append(c)
            vals.append(mu + rng.normal(0, 1))
    clubs += [S.ORG_UNKNOWN] * 5
    vals += [0.0] * 5
    t = S._fit_club_table(vals, clubs)
    raw = {c: np.mean([v for v, k in zip(vals, clubs) if k == c]) for c in ("BOS", "NYY")}
    assert math.isfinite(t["k"]) and t["k"] > 0
    for c in ("BOS", "NYY"):
        lo, hi = sorted((t["pooled"], raw[c]))
        assert lo < t["clubs"][c] < hi
    assert S._club_intercept(t, S.ORG_UNKNOWN) == t["pooled"]
    assert S._club_intercept(t, "MIA") == t["pooled"]
    flat = S._fit_club_table([0.0, 1.0, 0.0, 1.0], ["BOS", "BOS", "NYY", "NYY"])
    assert flat["k"] == math.inf and flat["clubs"] == {"BOS": 0.5, "NYY": 0.5}


def _out_row(key, V, status=S.ACTIVE, rung=2.0, age=0.0, climb=1.0, perf=None, pt=0.5,
             org="BOS", side="hit", resolved=True, gs=None):
    return {"player_key": key, "side": side, "vintage": V, "id_resolved": resolved,
            "rung_pre": rung, "age_pre": age, "climb_raw": climb, "perf_raw": perf,
            "pt_raw": pt, "gs_share_raw": gs, "org": org, "s5_status": status}


def _zero_maps(side="hit"):
    zero = {"by_rung": {}, "age_slope": 0.0, "pooled": 0.0, "n": 1}
    return {"side": side, "residual": {k: dict(zero) for k in S._map_keys(side)},
            "club": {"pooled": 0.0, "k": math.inf, "clubs": {}, "sizes": {}, "n": 1}}


def test_components_hitter_scalar_missing_perf_and_absent_codes():
    rows = [_out_row("a", 2015, perf={"obp_rel": 0.02, "contact": 0.01, "iso_rel": 0.0}),
            _out_row("b", 2015, perf={"obp_rel": -0.02, "contact": -0.01, "iso_rel": 0.02}),
            _out_row("c", 2015, perf={"obp_rel": 0.0, "contact": 0.0, "iso_rel": -0.02}),
            _out_row("m", 2015, climb=4.0, perf=None),
            _out_row("x", 2015, status=S.ABSENT_UNKNOWN, climb=None, perf=None, pt=0.0),
            _out_row("i", 2015, status=S.ABSENT_IDENTITY, climb=None, perf=None,
                     pt=None, resolved=False)]
    out = S._components(rows, _zero_maps())
    by = {r["player_key"]: r for r in out}
    zs = {k: [by[p]["z_" + k] for p in "abc"] for k in S.HIT_PERF}
    for k, v in zs.items():
        assert np.mean(v) == pytest.approx(0.0) and np.std(v) == pytest.approx(1.0)
    for p in "abc":
        assert by[p]["s3"] == pytest.approx(np.mean([by[p]["z_" + k] for k in S.HIT_PERF]))
    assert by["m"]["s3"] == 0.0 and by["x"]["s3"] == 0.0
    assert (by["x"]["absent"], by["a"]["absent"]) == (1.0, 0.0)
    assert by["x"]["s2"] == pytest.approx(np.mean([1.0, 1.0, 1.0, 4.0]))
    assert by["x"]["s4"] == 0.0
    assert all(by["i"][k] is None for k in S.FEATURES["hit"])
    assert "z_" + S.HIT_PERF[0] not in rows[0]                # inputs are not mutated


def test_components_demean_climb_by_the_club_table():
    maps = _zero_maps("pit")
    maps["club"] = {"pooled": 0.1, "k": 1.0, "clubs": {"BOS": 0.6}, "sizes": {}, "n": 1}
    rows = [_out_row("a", 2015, side="pit", perf={"k_minus_bb": 0.1}, gs=0.5),
            _out_row("b", 2015, side="pit", org=S.ORG_UNKNOWN, perf={"k_minus_bb": 0.0},
                     gs=0.0)]
    by = {r["player_key"]: r for r in S._components(rows, maps)}
    assert by["a"]["s2"] == pytest.approx(0.4)
    assert by["b"]["s2"] == pytest.approx(0.9)
    assert by["a"]["s4_gs"] == 0.5
    with pytest.raises(ValueError):
        S._components([_out_row("h", 2015)], maps)


def _fit_rows(n_per=40, vintages=S.FIT_VINTAGES, seed=7, side="hit"):
    rng = np.random.default_rng(seed)
    beta = {"s2": 0.5, "s3": -0.3, "s4": 0.2, "s4_gs": 0.1, "absent": -0.4}
    rows = []
    for V in vintages:
        for i in range(n_per):
            r = {"player_key": f"p{V}_{i}", "vintage": V, "side": side,
                 "id_resolved": True, "weight": 1.0}
            for k in S.FEATURES[side]:
                r[k] = float(rng.integers(0, 2)) if k == "absent" else float(rng.normal())
            r["target"] = sum(beta[k] * r[k] for k in S.FEATURES[side])
            r["target"] += 0.05 * float(rng.normal())
            rows.append(r)
    return rows, beta


def test_ridge_recovers_coefficients_with_a_small_penalty():
    rows, beta = _fit_rows()
    X = S._design(rows, S.FEATURES["hit"])
    y = np.asarray([r["target"] for r in rows])
    m = S._ridge_fit(X, y, np.ones(len(y)), 1e-6)
    got = m["beta"] / m["sd"]
    assert got == pytest.approx([beta[k] for k in S.FEATURES["hit"]], abs=0.03)


def test_alpha_selection_prefers_the_larger_penalty_on_a_tie():
    X = np.zeros((10, 2))
    y = np.arange(10.0)
    folds = np.asarray([0, 1] * 5)
    assert S._select_alpha(X, y, np.ones(10), folds) == max(S.RIDGE_GRID)


def test_lovo_predicts_each_vintage_from_the_others_only():
    rows, _ = _fit_rows()
    base = S._s_idx_oos(rows, S.FEATURES["hit"], "lovo")
    assert set(base["alphas"]) == set(S.FIT_VINTAGES)
    assert all(a in S.RIDGE_GRID for a in base["alphas"].values())
    moved = [dict(r, target=r["target"] + (5.0 if r["vintage"] == 2013 else 0.0))
             for r in rows]
    again = S._s_idx_oos(moved, S.FEATURES["hit"], "lovo")
    held = np.asarray([r["vintage"] == 2013 for r in rows])
    assert np.allclose(base["pred"][held], again["pred"][held])
    assert not np.allclose(base["pred"][~held], again["pred"][~held])


def test_grouped_folds_keep_a_player_on_one_side_and_are_seeded():
    keys = ["a", "b", "a", "c", "d", "b", "e", "f", "g", "h", "a"]
    f1 = S._player_folds(keys)
    f2 = S._player_folds(list(reversed(keys)))[::-1]
    assert np.array_equal(f1, f2)
    for k in set(keys):
        assert len({int(f) for f, kk in zip(f1, keys) if kk == k}) == 1
    assert set(f1.tolist()) <= set(range(S.N_FOLDS))
    rows, _ = _fit_rows(vintages=S.FALLBACK_VINTAGES)
    out = S._s_idx_oos(rows, S.FEATURES["hit"], "grouped")
    assert set(out["alphas"]) == set(range(S.N_FOLDS)) and not np.isnan(out["pred"]).any()
    full = S._s_idx_full(rows, S.FEATURES["hit"], "grouped")
    assert full["features"] == S.FEATURES["hit"] and full["alpha"] in S.RIDGE_GRID
    with pytest.raises(ValueError):
        S._s_idx_oos(rows, S.FEATURES["hit"], "kfold")


def _g_rows(seed=3, vintages=S.G_S_VINTAGES, side="pit"):
    rows, _ = _fit_rows(n_per=60, vintages=vintages, seed=seed, side=side)
    rng = np.random.default_rng(seed + 1)
    for r in rows:
        z = 1.2 * r["s2"] - 0.5
        r["reached"] = float(rng.random() < 1.0 / (1.0 + math.exp(-z)))
        r.pop("target")
    return rows


def test_g_s_is_forward_chained():
    rows = _g_rows()
    out = S._g_s_forward(rows, S.FEATURES["pit"])
    vint = np.asarray([r["vintage"] for r in rows])
    assert np.isnan(out["pred"][vint <= 2012]).all()
    assert not np.isnan(out["pred"][vint >= 2013]).any()
    assert ((out["pred"][vint >= 2013] > 0) & (out["pred"][vint >= 2013] < 1)).all()
    moved = [dict(r, reached=(1.0 - r["reached"]) if r["vintage"] >= 2016 else r["reached"])
             for r in rows]
    again = S._g_s_forward(moved, S.FEATURES["pit"])
    early = (vint >= 2013) & (vint <= 2016)
    assert np.allclose(out["pred"][early], again["pred"][early])


def test_g_s_fit_skips_unresolved_rows_and_reads_the_s2_channel():
    rows = _g_rows(vintages=(2011, 2012, 2013))
    rows.append(dict(rows[0], player_key="u", reached=None))
    m = S._g_s_fit(rows, S.FEATURES["pit"])
    assert m["features"] == S.FEATURES["pit"]
    assert m["b"][1 + S.FEATURES["pit"].index("s2")] > 0
    assert S._g_s_fit(rows[:5], S.FEATURES["pit"]) is None


def test_logit_is_finite_on_one_class_data():
    X = np.random.default_rng(0).normal(size=(30, 2))
    m = S._logit_fit(X, np.zeros(30), 10.0)
    p = S._logit_predict(m, X)
    assert np.isfinite(p).all() and (p < 0.5).all()


# ---------------------------------------------------------------------------
# 5. the Mexican League on the 2016 and 2019 files
# ---------------------------------------------------------------------------

@needs_cache
@pytest.mark.parametrize("season,total,mex", [(2016, 1627, 349), (2019, 1665, 336)])
def test_the_mexican_league_is_dropped(season, total, mex, fresh_store):
    lines = [ln for ln in S._season_lines(season, "hitting") if ln["sport"] == 11]
    assert len(lines) == total
    dropped = [ln for ln in lines if S._line_level(ln, season, "gate") is None]
    assert len(dropped) == mex
    assert all(ln["league"] == "MEX" for ln in dropped)
    assert all(S._line_level(ln, season, "efv_dataset") == "AAA" for ln in dropped)
    kept = [ln["row"] for ln in lines if ln["league"] != "MEX"]
    assert S._pure_norms(season, "AAA", "hitting") == \
        mh.level_norms_from_rows(kept, "hitting")
    assert S._pure_norms(season, "AAA", "hitting")["n"] < \
        mh.level_norms_from_rows([ln["row"] for ln in lines], "hitting")["n"]
    mex_only = {ln["id"] for ln in dropped} - {ln["id"] for ln in lines
                                               if ln["league"] != "MEX"}
    pid = sorted(mex_only)[0]
    pid_lines = S._season_index(season, "hitting")[pid]
    if all(ln["sport"] == 11 for ln in pid_lines):
        assert S._primary_level(pid_lines, "hit", season)[0] is None
        assert S._playing_time(pid_lines, season, "hit")["pt"] == 0.0
    tot = {}
    for ln in lines:
        if ln["league"] != "MEX":
            tot[ln["id"]] = tot.get(ln["id"], 0.0) + S._exposure(ln["row"], "hit")
    qual = [e for e in tot.values() if e >= 50]
    assert S._full_season_exposure(season, "AAA", "hit") == \
        pytest.approx(float(np.quantile(qual, S.FULL_SEASON_QUANTILE)))


@needs_cache
def test_short_season_a_is_its_own_rung_before_2021(fresh_store):
    ssa = [ln for ln in S._season_lines(2016, "pitching") if ln["sport"] == 15]
    assert ssa and all(S._line_level(ln, 2016, "gate") == "SSA" for ln in ssa)
    assert S._pure_norms(2016, "SSA", "pitching")["n"] > 0
    pins = json.loads((S.DATA_DIR / S.PINS_NAME).read_text(encoding="utf-8"))
    for season, groups in pins["transfer_seasons"].items():
        if int(season) >= S.LADDER_BREAK:
            assert all("15" not in g for g in groups.values()), season


# ---------------------------------------------------------------------------
# 6. the V-1 derivation reproduces the frame's level_rank (V 2015-2019)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dev_frames():
    if not HAS_CACHE:
        pytest.skip("no cache")
    import efv_vintage_frame as F
    saved = mh._fetch

    def boom(url):
        raise AssertionError(f"a frame build tried to fetch {url}")
    mh._fetch = boom
    try:
        u = F.load_universe()
        return {(side, V): F.build_frame(side, V, universe=u, sidecars=False)
                for side in S.SIDES for V in range(2015, 2020)}
    finally:
        mh._fetch = saved


def test_rung_pre_reproduces_the_frame_level_rank(dev_frames):
    """efv_dataset's rule read off the pinned store (the "efv_dataset" convention)
    gives the frame's level_rank and season on every row that carries a MiLB block
    read inside the store (2010 on). A block read off an older line is outside the
    pinned store and is named here; the test fails on any other difference."""
    carried = below_floor = 0
    misses = []
    for (side, V), rows in dev_frames.items():
        for r in rows:
            m = r.get("milb")
            if not m:
                continue
            carried += 1
            pre = S._pre_rung(r["mlbam_id"], V, side, "efv_dataset")
            if m["milb_season"] < S.STORE_FIRST:
                below_floor += 1
                assert pre["pre_absent"] or pre["rung_pre_season"] >= S.STORE_FIRST
                continue
            if (pre["rung_pre"], pre["rung_pre_season"]) != (m["level_rank"],
                                                              m["milb_season"]):
                misses.append((side, V, r["player_key"]))
    assert carried > 4000
    assert below_floor <= 5
    assert misses == []


def test_the_gate_convention_differs_only_by_its_two_registered_rules(dev_frames):
    for (side, V), rows in dev_frames.items():
        for r in rows:
            m = r.get("milb")
            if not m or m["milb_season"] < S.STORE_FIRST:
                continue
            g = S._pre_rung(r["mlbam_id"], V, side, "gate")
            if g["rung_pre"] == m["level_rank"]:
                continue
            if g["rung_pre_level"] == S.SSA_LEVEL:
                assert m["milb_level"] == "A", (side, V, r["player_key"])
                continue
            lines = S._season_index(m["milb_season"], S.GROUP[side])[r["mlbam_id"]]
            assert any(ln["league"] == S.MEX_LEAGUE for ln in lines), \
                (side, V, r["player_key"])


# ---------------------------------------------------------------------------
# 7. the league-wide shape test (no frame row, no score, no label)
# ---------------------------------------------------------------------------

#: S1 per (side, season) for every player with an affiliated line in the file: the rung
#: name, MLB for the event, ABSENT_UNKNOWN for a player whose only lines are Mexican
#: League (the 2018 sportId 11 files carry no Mexican League line).
SHAPE = {
    ("hit", 2015): {"A": 496, "A+": 452, "AA": 710, "AAA": 506, "ABSENT_UNKNOWN": 320,
                    "CPX": 790, "DSL": 693, "MLB": 643, "SSA": 328},
    ("hit", 2016): {"A": 486, "A+": 463, "AA": 710, "AAA": 517, "ABSENT_UNKNOWN": 343,
                    "CPX": 805, "DSL": 702, "MLB": 661, "SSA": 330},
    ("hit", 2017): {"A": 490, "A+": 483, "AA": 743, "AAA": 531, "ABSENT_UNKNOWN": 336,
                    "CPX": 832, "DSL": 664, "MLB": 627, "SSA": 364},
    ("hit", 2018): {"A": 498, "A+": 476, "AA": 730, "AAA": 519, "CPX": 873,
                    "DSL": 722, "MLB": 673, "SSA": 351},
    ("hit", 2019): {"A": 520, "A+": 496, "AA": 746, "AAA": 535, "ABSENT_UNKNOWN": 329,
                    "CPX": 677, "DSL": 746, "MLB": 675, "SSA": 352},
    ("pit", 2015): {"A": 505, "A+": 514, "AA": 488, "AAA": 380, "ABSENT_UNKNOWN": 349,
                    "CPX": 885, "DSL": 786, "MLB": 498, "SSA": 389},
    ("pit", 2016): {"A": 541, "A+": 521, "AA": 466, "AAA": 397, "ABSENT_UNKNOWN": 350,
                    "CPX": 914, "DSL": 781, "MLB": 502, "SSA": 384},
    ("pit", 2017): {"A": 545, "A+": 531, "AA": 494, "AAA": 411, "ABSENT_UNKNOWN": 354,
                    "CPX": 976, "DSL": 747, "MLB": 534, "SSA": 404},
    ("pit", 2018): {"A": 524, "A+": 532, "AA": 510, "AAA": 391, "CPX": 1059,
                    "DSL": 838, "MLB": 546, "SSA": 400},
    ("pit", 2019): {"A": 579, "A+": 553, "AA": 492, "AAA": 438, "ABSENT_UNKNOWN": 401,
                    "CPX": 834, "DSL": 893, "MLB": 553, "SSA": 423},
}
#: Players in the file with no store line in any season from 2010 to V - 1.
PRE_ABSENT = {("hit", 2015): 1422, ("hit", 2016): 1442, ("hit", 2017): 1407,
              ("hit", 2018): 1342, ("hit", 2019): 1394, ("pit", 2015): 1403,
              ("pit", 2016): 1403, ("pit", 2017): 1472, ("pit", 2018): 1361,
              ("pit", 2019): 1516}


@needs_cache
@pytest.mark.parametrize("side,season", sorted(SHAPE))
def test_league_wide_shape(side, season):
    tj = S._tj_index()
    idx = S._season_index(season, S.GROUP[side])
    s1: dict[str, int] = {}
    pre_absent = 0
    for pid in sorted(idx):
        pre = S._pre_rung(pid, season, side)
        o = S._season_outcome(pid, season, side, tj, pre["rung_pre"])
        key = o["end_level"] if o["level_end"] is not None else o["s5_status"]
        s1[key] = s1.get(key, 0) + 1
        pre_absent += pre["pre_absent"]
        c = o["climb_raw"]
        if c is not None:
            assert -S.MLB_RUNG <= c <= S.MLB_RUNG and (2 * c) == int(2 * c)
            assert c == o["level_end"] - pre["rung_pre"]
        else:
            assert pre["pre_absent"] or o["level_end"] is None
        if o["s5_status"] == S.ABSENT_UNKNOWN:
            assert all(ln["sport"] == 11 and ln["league"] == S.MEX_LEAGUE
                       for ln in idx[pid])
    assert dict(sorted(s1.items())) == SHAPE[(side, season)]
    assert sum(s1.values()) == len(idx)
    assert pre_absent == PRE_ABSENT[(side, season)]
