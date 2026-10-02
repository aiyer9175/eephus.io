# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-04: the provisional freeze scorer (provisional_track.py) and its artifact.

Acceptance (PROVISIONAL_V2.md section 4): the served 2026-06-23 artifact, replayed as a
backdated freeze to 2026-09-24, reproduces the research lane's 97 pairs, median lead
48 days and selection AUC 0.826; the committed 2026-09-25 freeze scores 0 labels
through 2026-10-01. Also pinned on synthetic data: the label date is the first-seen
date (a Pipeline row whose snapshot_date the daily capture bumped past the freeze is
still a pre-freeze opinion), interim rows say "window open" and carry no claims, the
artifact is append-only and survives a revert of the tracked file, and the scorer
reads no WAR.

The two acceptance tests read the local prospects.db and served identity maps (read
only) and skip where those are absent; every write goes to tmp_path.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import provisional_track as T

ROOT = Path(__file__).resolve().parent
FREEZE = ROOT / "data" / "provisional_freeze" / "FREEZE_provisional_2026-09-25.json"


def _real_inputs_or_skip():
    if not (ROOT / "prospects.db").exists():
        pytest.skip("prospects.db not on this machine")
    for f in ("timeseries.json", "xfv.json", "rosters_by_org.json"):
        if not (ROOT / "data" / f).exists():
            pytest.skip(f"data/{f} not built")


@pytest.fixture(scope="module")
def real_inputs():
    _real_inputs_or_skip()
    return T.identity(), T.opinions()


def test_backdated_replay_reproduces_the_lane(real_inputs):
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    try:
        fz = T.backdated_freeze()
    except subprocess.CalledProcessError:
        pytest.skip(f"commit {T.BACKDATED['commit']} not in this clone")
    m2k, opin = real_inputs
    res = T.score(fz, T.BACKDATED["window_end"], B=200, m2k=m2k, opin=opin)
    a = res["ANY"]
    assert a["level"]["n_first_fv"] == 97
    assert a["graded_in_window"] == 97
    assert a["level"]["median_lead_days"] == 48
    assert round(a["selection"]["grade"]["auc"], 3) == 0.826
    assert a["level"]["grade"]["spearman"] == 0.017
    assert (a["level"]["grade"]["mae"], a["level"]["grade"]["mae_null_const"]) == (6.21, 4.54)
    assert res["coverage"]["matched_to_freeze"] == 97


def test_todays_freeze_scores_zero_labels(real_inputs):
    m2k, opin = real_inputs
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    res = T.score(fz, "2026-10-01", B=50, m2k=m2k, opin=opin)
    for s in T.SETS:
        assert res[s]["graded_in_window"] == 0, s
        assert res[s]["level"]["n_first_fv"] == 0, s
    assert res["coverage"]["first_opinion_in_window"] == 0
    assert res["n_rows"] == 6066


# --- synthetic --------------------------------------------------------------------

def _world(tmp_path: Path, snaps: list[tuple]) -> dict:
    """A data dir, a DB and a freeze dir. snaps: (player_key, source, snapshot_date,
    inserted_at, fv)."""
    d = tmp_path / "data"
    (d / "fz").mkdir(parents=True)
    (d / "timeseries.json").write_text(json.dumps({"players": [
        {"player_key": "ann", "mlbam_id": 1}, {"player_key": "bob", "mlbam_id": 2},
        {"player_key": "cal", "mlbam_id": 3}]}), encoding="utf-8")
    (d / "xfv.json").write_text(json.dumps({"by_player": {}}), encoding="utf-8")
    (d / "rosters_by_org.json").write_text(json.dumps({}), encoding="utf-8")
    db = tmp_path / "p.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE snapshots (source TEXT, snapshot_date TEXT, player_key TEXT, "
                "rank INTEGER, fv REAL, fv_plus INTEGER DEFAULT 0, inserted_at TEXT)")
    for pk, src, sd, ins, fv in snaps:
        con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,0,?)", (src, sd, pk, None, fv, ins))
    con.commit()
    con.close()
    rows = [{"key": f"mlbam_{i}", "mlbam": i, "side": "H", "level": lv, "age": 19.0, "grade": g}
            for i, lv, g in ((1, "A", 40.0), (2, "DSL", 25.0), (3, "CPX", 30.0))]
    fz = {"frozen_at": "2026-09-25", "windows": {"W6": "2027-04-15"},
          "nulls": {"ANY": 37.5}, "sha256_rows": T.canon_rows(rows), "rows": rows}
    (d / "fz" / "FREEZE_provisional_2026-09-25.json").write_text(json.dumps(fz), encoding="utf-8")
    return {"data_dir": d, "db_path": db, "freeze_dir": d / "fz", "fz": fz}


def test_a_bumped_pipeline_row_is_a_pre_freeze_opinion_not_a_label(tmp_path):
    w = _world(tmp_path, [
        # bob: on a Pipeline Top 30 since August, re-stamped by the daily capture on 09-30
        ("bob", "mlb_pipeline", "2026-09-30", "2026-08-14 03:00:00", 40.0),
        # ann: a genuine first grade after the freeze
        ("ann", "fangraphs", "2026-11-06", "2026-11-06 21:00:00", 40.0),
    ])
    opin = T.opinions(w["db_path"])
    assert opin["bob"][0][0] == "2026-08-14"
    res = T.score(w["fz"], "2026-12-01", B=20, m2k=T.identity(w["data_dir"]), opin=opin)
    assert res["dropped"]["opinion_on_or_before_freeze"] == 1
    assert res["ANY"]["graded_in_window"] == 1
    assert res["ANY"]["level"]["label_dates"] == {"2026-11-06": 1}
    assert res["coverage"]["first_opinion_in_window"] == 1


def test_interim_rows_say_window_open_and_carry_no_claims(tmp_path):
    w = _world(tmp_path, [("ann", "fangraphs", "2026-11-06", "2026-11-06 21:00:00", 40.0)])
    kw = dict(freeze_dir=w["freeze_dir"], data_dir=w["data_dir"], db_path=w["db_path"], B=50,
              retrospective=False)
    rows = T.build_rows("2026-12-01", **kw)
    assert [r["status"] for r in rows] == ["window open until 2027-04-15"]
    assert rows[0]["claims"] is None and rows[0]["verdict_readable"] is False
    assert rows[0]["scored_through"] == "2026-12-01"
    closed = T.build_rows("2027-04-16", **kw)
    assert closed[0]["status"] == "window closed 2027-04-15"
    assert closed[0]["verdict_readable"] is True and closed[0]["scored_through"] == "2027-04-15"
    assert closed[0]["claims"] is not None
    assert T.build_rows("2026-09-25", **kw) == []          # nothing to score on the freeze day


def test_the_artifact_is_append_only_and_survives_a_revert(tmp_path):
    w = _world(tmp_path, [])
    out, led = tmp_path / "eval.json", tmp_path / "cache" / "ledger.jsonl"
    kw = dict(freeze_dir=w["freeze_dir"], data_dir=w["data_dir"], db_path=w["db_path"], B=20,
              retrospective=False, out_path=out, ledger_path=led)
    r1 = T.update("2026-10-01", now_iso="2026-10-01T09:00:00+00:00", **kw)
    assert len(r1["appended"]) == 1
    committed = out.read_bytes()
    r2 = T.update("2026-10-02", now_iso="2026-10-02T09:00:00+00:00", **kw)
    assert r2["appended"] == [] and r2["n_rows"] == 1          # nothing measured changed
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["rows"][0]["last_verified_at"] == "2026-10-02T09:00:00+00:00"
    # A first grade lands; the next night appends, the first row is kept unchanged.
    con = sqlite3.connect(w["db_path"])
    con.execute("INSERT INTO snapshots VALUES ('fangraphs','2026-11-06','ann',NULL,40.0,0,"
                "'2026-11-06 21:00:00')")
    con.commit()
    con.close()
    r3 = T.update("2026-11-07", now_iso="2026-11-07T09:00:00+00:00", **kw)
    assert len(r3["appended"]) == 1
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert [r["as_of"] for r in doc["rows"]] == ["2026-10-01", "2026-11-07"]
    assert doc["rows"][1]["result"]["ANY"]["graded_in_window"] == 1
    assert doc["latest"]["prospective|FREEZE_provisional_2026-09-25.json|W6"].endswith("2026-11-07")
    # The box's git checkout restores the older tracked file; the next night merges back.
    out.write_bytes(committed)
    T.update("2026-11-08", now_iso="2026-11-08T09:00:00+00:00", **kw)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert [r["as_of"] for r in doc["rows"]] == ["2026-10-01", "2026-11-07"]
    assert len(led.read_text(encoding="utf-8").splitlines()) == 2


def test_a_tampered_freeze_is_refused(tmp_path):
    w = _world(tmp_path, [])
    fz = dict(w["fz"])
    fz["rows"] = [dict(r) for r in fz["rows"]]
    fz["rows"][0]["grade"] = 55.0
    with pytest.raises(ValueError):
        T.score(fz, "2026-10-01", B=10, m2k={}, opin={})


def test_the_scorer_reads_no_war():
    src = (ROOT / "provisional_track.py").read_text(encoding="utf-8")
    for tok in ("career_war", "realized_war", "xfv_war", "war6", "target_censored"):
        assert tok not in src, tok
    q = src[src.index("def opinions("):src.index("def backdated_freeze(")]
    assert "from snapshots" in q and "war" not in q.lower()


def test_the_committed_artifact_reads_as_the_rules_say():
    p = ROOT / "data" / "provisional_track_eval.json"
    if not p.exists():
        pytest.skip("artifact not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["model_id"] == "provisional_first_grade" and doc["generated_at"]
    assert doc["reads_no_war"] is True
    rows = {r["run_id"]: r for r in doc["rows"]}
    for rid in doc["latest"].values():
        r = rows[rid]
        if r["leg"] == "prospective" and r["as_of"] < r["window_end"]:
            assert r["status"] == f"window open until {r['window_end']}" and r["claims"] is None
        if r["leg"] == "served_backdated":
            a = r["result"]["ANY"]
            assert (a["level"]["n_first_fv"], a["level"]["median_lead_days"]) == (97, 48)
            assert round(a["selection"]["grade"]["auc"], 3) == 0.826


def test_the_registry_rows_quote_the_artifact():
    """PV-05: provisional_first_grade and the xfv_ungraded amendment print the spent
    replay's figures exactly as data/provisional_track_eval.json carries them."""
    p = ROOT / "data" / "provisional_track_eval.json"
    if not p.exists():
        pytest.skip("artifact not built")
    doc = json.loads(p.read_text(encoding="utf-8"))
    bd = {r["run_id"]: r for r in doc["rows"]}[doc["latest"]["served_backdated|git:f6dc2c8a|spent"]]
    a = bd["result"]["ANY"]
    reg = {m["model_id"]: m for m in json.loads(
        (ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))["models"]}
    row = reg["provisional_first_grade"]
    assert row["eval_artifact"] == "data/provisional_track_eval.json"
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "shipped_partial_measurement"
    lg = a["level"]["grade"]
    for want in (f"drew {a['level']['n_first_fv']} first grades",
                 f"selection AUC {a['selection']['grade']['auc']:.3f}",
                 f"level-rank null {a['selection']['null_level_rank']['auc']:.3f}",
                 f"Spearman {lg['spearman']:.3f}", f"MAE {lg['mae']} against {lg['mae_null_const']}",
                 f"Median lead {a['level']['median_lead_days']} days"):
        assert want in row["notes"], want
    xu = reg["xfv_ungraded"]["notes"]
    assert f"MAE {lg['mae']} against {lg['mae_null_const']} for a constant, n {lg['n']}" in xu


# --- PV-08 receipts (by_player) ----------------------------------------------------

def test_receipts_record_the_frozen_grade_and_the_first_grade_after_it(tmp_path):
    w = _world(tmp_path, [
        # ann: FanGraphs 35+ after the freeze (coded 37.5), then Pipeline later
        ("ann", "fangraphs", "2026-11-06", "2026-11-06 21:00:00", 37.5),
        ("ann", "mlb_pipeline", "2027-01-22", "2027-01-22 05:00:00", 40.0),
        # bob: an opinion before the freeze, so he is not eligible and has no receipt
        ("bob", "baseballamerica", "2026-08-10", "2026-08-10 03:00:00", 35.0),
    ])
    rec = T.receipts("2026-12-01", freeze_dir=w["freeze_dir"], m2k=T.identity(w["data_dir"]),
                     opin=T.opinions(w["db_path"]))
    assert rec["columns"] == T.RECEIPT_COLUMNS
    fz = rec["freezes"]["FREEZE_provisional_2026-09-25.json"]
    assert fz["frozen_at"] == "2026-09-25" and fz["scored_through"] == "2026-12-01"
    rows = fz["rows"]
    assert "mlbam_2" not in rows, "a pre-freeze opinion drops the row, as score() does"
    col = {c: i for i, c in enumerate(T.RECEIPT_COLUMNS)}
    ann = rows["mlbam_1"]
    assert ann[col["grade"]] == 40.0, "the frozen grade is the freeze file's own value"
    assert ann[col["first_date"]] == "2026-11-06" and ann[col["first_source"]] == "fangraphs"
    assert ann[col["first_label"]] == "35+" and ann[col["lead_days"]] == 42
    assert ann[col["player_key"]] == "ann"
    cal = rows["mlbam_3"]
    assert cal[col["grade"]] == 30.0 and cal[col["first_date"]] is None
    assert fz["n_first_graded"] == 1
    # Nothing to receipt on the freeze day itself.
    assert T.receipts("2026-09-25", freeze_dir=w["freeze_dir"], m2k={}, opin={})["freezes"] == {}


def test_receipts_ride_the_artifact_and_survive_a_rows_only_commit(tmp_path):
    w = _world(tmp_path, [("ann", "fangraphs", "2026-11-06", "2026-11-06 21:00:00", 40.0)])
    out, led = tmp_path / "eval.json", tmp_path / "cache" / "ledger.jsonl"
    T.update("2026-11-07", out_path=out, ledger_path=led, freeze_dir=w["freeze_dir"],
             data_dir=w["data_dir"], db_path=w["db_path"], B=20, retrospective=False,
             now_iso="2026-11-07T09:00:00+00:00")
    text = out.read_text(encoding="utf-8")
    doc = json.loads(text)
    rows = doc["by_player"]["freezes"]["FREEZE_provisional_2026-09-25.json"]["rows"]
    assert set(rows) == {"mlbam_1", "mlbam_2", "mlbam_3"}
    # one receipt per line: the compact block, not one value per line
    assert '"mlbam_1": [40.0,"2026-11-06","fangraphs",40.0,"40",42,"ann"]' in text
    # a commit that brings no receipts keeps the previous block
    T.commit_rows([], out_path=out, ledger_path=led, now_iso="2026-11-08T09:00:00+00:00")
    assert json.loads(out.read_text(encoding="utf-8"))["by_player"] == doc["by_player"]


def test_the_committed_receipts_copy_the_freeze_grades():
    p = ROOT / "data" / "provisional_track_eval.json"
    if not p.exists():
        pytest.skip("artifact not built")
    bp = json.loads(p.read_text(encoding="utf-8")).get("by_player")
    if not bp:
        pytest.skip("artifact predates the receipts block")
    fz = json.loads(FREEZE.read_text(encoding="utf-8"))
    frozen = {str(r["key"]): r.get("grade") for r in fz["rows"]}
    rows = bp["freezes"][FREEZE.name]["rows"]
    gi = bp["columns"].index("grade")
    assert len(rows) > 5000
    bad = [k for k, v in rows.items()
           if (v[gi] is None) != (frozen.get(k) is None)
           or (v[gi] is not None and abs(v[gi] - round(float(frozen[k]), 1)) > 1e-9)]
    assert not bad, f"receipt grades that are not the freeze's: {bad[:5]}"
