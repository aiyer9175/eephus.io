# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the wave-2 injured-list family (efv_w2_il_backfill.py, EFV4_IL_BACKFILL).

1. Parsing: the feed's placement, activation, transfer and release rows become stints,
   paired by person id; a transfer to the 60-day list marks the stint severe on the day
   it was announced; an activation with nothing open is an orphan.
2. As of: only facts announced strictly before the cutoff enter; an activation after
   the cutoff never moves a value (fixture leakage test); the window is the declared
   number of seasons, cut at the feed's first complete year.
3. Ids: a list-vintage row reads its outcome-blind id, never record_mlbam_id; no id
   reads None; a resolved id with no stint reads 0.
4. The arms: fifteen, timing on both sides and skill on pitchers, registered in the
   screening lab's wave 2 without touching wave 1, buildable through column_values.
5. Bans: reserved list vintages raise, the 2025 cohort is skipped on the vm read,
   nothing is grouped by consensus-FV level, no served exporter, no em-dash.
6. The artifacts, when present: the stint table, the development read on the frozen
   label, the spent block labelled and never a ledger row.
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
import efv_w2_il_backfill as M  # noqa: E402

SRC = ROOT / "efv_w2_il_backfill.py"
PID = 900001


def _tx(tid, day, desc, *, code="SC", eff=None, pid=PID):
    return {"id": tid, "person": {"id": pid}, "date": day, "effectiveDate": eff or day,
            "typeCode": code, "description": desc, "toTeam": {"id": 1}}


def _stints(txs, pid=PID):
    ev = M.events_from_feed(txs)
    return M.stints_from_events(ev.get(pid, []))


# ---------------------------------------------------------------------------
# 1. parsing
# ---------------------------------------------------------------------------

def test_classify_reads_every_feed_template():
    assert M.classify("Erie SeaWolves placed RHP A on the 7-day disabled list.", "SC") == (
        "place", ["7"])
    assert M.classify("X placed LF B on the 7-day disabled list retroactive to May 31, "
                      "2015.", "SC") == ("place", ["7"])
    assert M.classify("X activated SS C from the 60-day injured list.", "SC") == (
        "activate", ["60"])
    assert M.classify("X transferred RHP D from the 7-day disabled list to the 60-day "
                      "disabled list.", "SC") == ("transfer", ["7", "60"])
    assert M.classify("X placed RHP E on the full-season injured list.", "SC") == (
        "place", ["full"])
    assert M.classify("X placed P F on the 10 day disabled list.", "SC") == ("place", ["10"])
    assert M.classify("X placed RHP G on the injured list.", "SC") == ("place", ["na"])
    assert M.classify("X recalled RHP H from Y. Placed on the 60-day injured list.",
                      "CU") == ("place", ["60"])
    assert M.classify("X released RF I.", "REL") == ("close", [])
    assert M.classify("X activated 2B J from the restricted list.", "SC") == (None, [])


def test_retroactive_start_and_pairing():
    st, orph = _stints([
        _tx(1, "2015-06-01", "A placed LF B on the 7-day disabled list retroactive to "
            "May 30, 2015.", eff="2015-05-30"),
        _tx(2, "2015-06-20", "A activated LF B from the 7-day disabled list."),
    ])
    assert orph == 0 and len(st) == 1
    s = st[0]
    assert (s["start"], s["placed"], s["end"], s["how"]) == (
        "2015-05-30", "2015-06-01", "2015-06-20", "activated")
    assert s["list"] == "7" and not s["severe"]


def test_transfer_marks_severe_on_its_day_and_orphans_are_counted():
    st, orph = _stints([
        _tx(1, "2016-04-10", "A placed RHP B on the 7-day disabled list."),
        _tx(2, "2016-05-15", "A transferred RHP B from the 7-day disabled list to the "
            "60-day disabled list."),
        _tx(3, "2016-08-01", "A activated RHP B from the 60-day disabled list."),
        _tx(4, "2016-09-01", "A activated RHP B from the 7-day disabled list."),
    ])
    assert len(st) == 1 and orph == 1
    assert st[0]["severe"] and st[0]["severe_announced"] == "2016-05-15"


def test_a_new_placement_or_a_release_closes_an_open_stint():
    st, _ = _stints([
        _tx(1, "2017-05-01", "A placed SS B on the 7-day disabled list."),
        _tx(2, "2017-07-01", "A placed SS B on the 7-day disabled list."),
        _tx(3, "2017-08-01", "A released SS B.", code="REL"),
    ])
    assert [s["how"] for s in st] == ["next_placement", "released"]
    assert st[0]["end"] == "2017-07-01"


# ---------------------------------------------------------------------------
# 2. as of
# ---------------------------------------------------------------------------

def _index(rows):
    return M.index_from_rows([[PID, *r] for r in rows])


ROWS = [
    # start, placed, list, severe, severe_announced, end, end_announced, how, team, inferred
    ["2014-05-01", "2014-05-01", "7", 0, None, "2014-05-21", "2014-05-21", "activated", 1, 0],
    ["2015-06-01", "2015-06-01", "60", 1, "2015-06-01", "2015-08-30", "2015-08-30",
     "activated", 1, 0],
    ["2016-07-01", "2016-07-01", "7", 0, None, "2017-04-10", "2017-04-10", "activated", 1, 0],
]


def test_a_fact_after_the_read_never_moves_a_value():
    idx = _index(ROWS)
    before = M.asof(PID, "2017-01-01", idx)
    assert before == {"il_stints_pre": 3.0, "il_days_pre": before["il_days_pre"],
                      "il_60day_pre": 1.0, "il_open_at_read": 1.0, "il_recurrent_pre": 1.0}
    # the 2016 stint's activation came after the read: its days stop at the season close
    assert before["il_days_pre"] == 20 + 90 + 92
    later = ROWS + [["2017-03-01", "2017-03-01", "60", 1, "2017-03-01", None, None, None,
                     1, 0]]
    idx2 = _index(later)
    assert M.asof(PID, "2017-01-01", idx2) == before
    # read after the activation: the stint is closed, no longer open
    after = M.asof(PID, "2018-01-01", idx2)
    assert after["il_open_at_read"] == 1.0 and after["il_stints_pre"] == 4.0


def test_the_window_is_the_declared_seasons_cut_at_the_feed_start():
    idx = _index(ROWS)
    assert M.LOOKBACK_SEASONS == 4
    # read at 2020: seasons 2016 to 2019, so only the 2016 stint is inside
    v = M.asof(PID, "2020-01-01", idx)
    assert v["il_stints_pre"] == 1.0 and v["il_open_at_read"] == 0.0
    assert M.window("2010-01-01")[0].isoformat() == "2009-01-01"
    assert M.window("2009-01-01") is None


def test_season_days_counts_april_to_september_only():
    from datetime import date
    assert M.season_days(date(2015, 3, 1), date(2015, 4, 11)) == 10
    assert M.season_days(date(2015, 9, 20), date(2016, 4, 6)) == 11 + 5
    assert M.season_days(date(2015, 5, 1), date(2015, 5, 1)) == 0


def test_no_id_reads_none_and_no_stint_reads_zero():
    idx = _index(ROWS)
    assert all(v is None for v in M.asof(None, "2017-01-01", idx).values())
    z = M.asof(PID + 7, "2017-01-01", idx)
    assert all(v == 0.0 for v in z.values())


def test_the_days_column_is_log1p_and_counts_are_raw():
    assert M.transformed("il_days_pre", 0.0) == 0.0
    assert M.transformed("il_days_pre", 9.0) == pytest.approx(2.302585093)
    assert M.transformed("il_stints_pre", 3.0) == 3.0
    assert M.transformed("il_stints_pre", None) is None


# ---------------------------------------------------------------------------
# 3. ids
# ---------------------------------------------------------------------------

def test_lv_reads_use_the_outcome_blind_id_at_v_jan_1(monkeypatch):
    idx = _index(ROWS)
    rows = [{"player_key": "x", "mlbam_id": PID, "record_mlbam_id": None, "vintage": 2017,
             "window": ["2017-01-01", "2017-05-01"]},
            {"player_key": "y", "mlbam_id": None, "record_mlbam_id": PID, "vintage": 2017,
             "window": ["2017-01-01", "2017-05-01"]}]
    out = M.lv_reads("pit", {"pit": {2017: (rows, [{}, {}])}}, index=idx)
    assert out[(2017, "x")]["il_stints_pre"] == 3.0
    assert out[(2017, "y")]["il_stints_pre"] is None


def test_vm_reads_take_the_earlier_cutoff_and_skip_the_reserved_cohort():
    idx = _index(ROWS)
    data = [{"player_key": "a", "decision_year": 2018},
            {"player_key": "b", "decision_year": F.R_VM_FIRST_DEBUT_YEAR}]
    raw = {"a": {"mlbam_id": PID, "cutoff": "2017-08-01"},
           "b": {"mlbam_id": PID, "cutoff": "2025-06-01"}}
    assert M.vm_cutoff(raw["a"], 2018) == "2017-08-01"
    assert M.vm_cutoff({"cutoff": "2019-06-01"}, 2019) == "2019-01-01"
    out = M.vm_reads("hit", data, raw, index=idx)
    assert set(out) == {"a"}
    # as of 2017-08-01 the 2016 stint is closed only in April 2017: known, not open
    assert out["a"]["il_open_at_read"] == 0.0 and out["a"]["il_stints_pre"] == 3.0


# ---------------------------------------------------------------------------
# 4. the arms and their registration
# ---------------------------------------------------------------------------

def test_the_arms_are_fifteen_and_registered_in_wave_two():
    names = [a["name"] for a in M.ARMS]
    assert len(names) == 15 == len(set(names))
    heads = {(a["head"], a["side"]) for a in M.ARMS}
    assert heads == {("timing", "hit"), ("timing", "pit"), ("skill", "pit")}
    for a in M.ARMS:
        assert a["stat"] in M.COLUMNS and not a["retest"] and a["kind"] == "column"
        assert a["column"] == {"source": "module", "module": "efv_w2_il_backfill",
                               "attr": "screen_column", "arg": a["stat"]}
    assert "efv_w2_il_backfill" in LAB.WAVE2_ARM_MODULES
    assert "efv_w2_milb" in LAB.WAVE2_ARM_MODULES
    assert set(names) <= {a["name"] for a in LAB.wave2_candidates()}
    assert LAB.registration_echo()["family_size"] == 7


def test_the_lab_builds_an_arm_through_its_own_column_values(monkeypatch):
    idx = _index(ROWS)
    monkeypatch.setattr(M, "stint_index", lambda path=M.TABLE_PATH: idx)
    M._LV_MEMO.clear()
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2018,
             "window": ["2018-01-01", "2018-05-01"]}]
    frames = {"pit": {2018: (rows, [{}])}}
    arm = next(a for a in M.ARMS if a["name"] == "w2i_days_skill_pit")
    vals = LAB.column_values(arm, frames)
    assert set(vals) == {(2018, "x")} and vals[(2018, "x")] > 0
    with pytest.raises(ValueError):
        M.screen_column("il_absent", "pit", frames)
    M._LV_MEMO.clear()


def test_the_v3_registration_is_scoped_and_restored():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    with M.registered_v3_columns() as cols:
        for a in M.ARMS:
            assert cols[a["name"]]["side"] == a["side"]
            assert cols[a["name"]]["head"] == a["head"]
            assert cols[a["name"]]["key"].startswith("scr_")
    assert V3.W2_COLUMNS == before


# ---------------------------------------------------------------------------
# 5. bans
# ---------------------------------------------------------------------------

def test_reserved_list_vintages_raise():
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2020,
             "window": ["2020-01-01", "2020-05-01"]}]
    with pytest.raises(F.ReservedFrameError):
        M.lv_reads("hit", {"hit": {2020: (rows, [{}])}}, index=_index(ROWS))


_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
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
    # a column builder reads no label, realized value or debut
    for fn in ("asof", "lv_reads", "vm_reads", "vm_cutoff", "screen_column", "window",
               "events_from_feed", "stints_from_events", "build_table"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        low = body.lower().replace("r_vm_first_debut_year", "")
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            assert banned not in low, (fn, banned)


# ---------------------------------------------------------------------------
# 6. the artifacts
# ---------------------------------------------------------------------------

def _load(path):
    if not path.exists():
        pytest.skip(f"{path.name} not built on this tree")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_stint_table_is_consistent():
    d = _load(M.TABLE_PATH)
    assert d["columns"] == list(M.TABLE_COLUMNS)
    assert d["n_stints"] == len(d["rows"])
    assert d["source"]["complete_from"] == 2009
    for r in d["rows"][:2000]:
        s = dict(zip(d["columns"], r))
        assert s["start"] <= s["placed"]
        assert s["end"] is None or s["end"] >= s["start"]
        assert s["list"] in {"7", "10", "15", "60", "full", "na"}


def test_the_artifact_is_a_development_read_with_a_labelled_spent_block():
    d = _load(M.OUT_PATH)
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["exploratory"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["label"]["id"].startswith("fwar@2026-10-02")
    assert d["ground_truth_rerun"]["trigger_cleared_both_sides"] is True
    assert d["lv_dev"]["frame"]["folds"] == [2017, 2018, 2019]
    assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in d["vm_dev"]["frame"]["fold_years"])
    assert all(p["mismatched_base_order"] == 0 for p in d["vm_dev"]["parity"].values())
    for side, cov in d["lv_dev"]["coverage"].items():
        assert not ({"2020", "2021"} & set(cov)), side
    for a in M.ARMS:
        for fid in ("lv_dev", "vm_dev"):
            blk = d[fid]["arms"][a["name"]]["frame"]
            for comp in ("candidate_vs_efv_v2_base", "candidate_vs_prospx_consensus"):
                leg = blk["deltas"][comp]["spearman"]
                assert leg["delta"] is not None and len(leg["ci95"]) == 2
    sp = d.get("spent")
    if sp:
        assert sp["label"] == M.SPENT_LABEL and sp["selects"] is False
        for a in sp["arms"].values():
            assert a["label"] == M.SPENT_LABEL
            assert set(a["frames"]) == {"lv_res", "vm_pros"}


def test_the_ledger_rows_are_this_modules_development_rows_only():
    d = _load(M.OUT_PATH)
    docs = M.ledger_docs(d)
    assert len(docs) == 2 * len(M.ARMS)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(M.MODEL_PREFIX)
        assert set(doc["frames"]) <= {"lv_dev", "vm_dev"}
