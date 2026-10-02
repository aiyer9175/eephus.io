# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/grpo_forward_lab.py on SYNTHETIC fixtures only
(docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md section 2).

Never reads prospects.db: every run here points --db at a tmp fixture and
--out at a tmp artifact, and the last test proves data/grpo_forward_eval.json
is untouched by the module.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from editorial_eval import HIT_RULES
from tools import grpo_forward_lab as lab

ROOT = Path(__file__).resolve().parent
REAL_OUT = ROOT / "data" / "grpo_forward_eval.json"


def _digest(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _make_db(path: Path, scores: dict, board: dict, pk: bool = True) -> Path:
    """scores {date: {key: score|None}}; board {night: {key: (fv, rank)}}.
    The archive table allows NULL scores so the null path can be driven."""
    con = sqlite3.connect(path)
    key = ", PRIMARY KEY (snapshot_date, player_key)" if pk else ""
    con.execute("CREATE TABLE grpo_score_history (snapshot_date TEXT NOT NULL, "
                f"player_key TEXT NOT NULL, score REAL{key})")
    con.execute("CREATE TABLE metric_snapshots (player_key TEXT NOT NULL, "
                "snapshot_date TEXT NOT NULL, overall_rank INTEGER, consensus_fv REAL)")
    for d, rows in scores.items():
        con.executemany("INSERT INTO grpo_score_history VALUES (?,?,?)",
                        [(d, k, s) for k, s in rows.items()])
    for n, rows in board.items():
        con.executemany("INSERT INTO metric_snapshots VALUES (?,?,?,?)",
                        [(k, n, r, fv) for k, (fv, r) in rows.items()])
    con.commit()
    con.close()
    return path


def _validated_fixture(tmp_path: Path) -> Path:
    """100 players; the top 10 by score are the only risers; Control B (all FV
    tied, ranks reversed) picks the bottom 10 by score. Badge clears both."""
    keys = [f"p{i:03d}" for i in range(100)]
    sc = {k: i / 100 for i, k in enumerate(keys)}
    cohorts = ("2026-08-19", "2026-08-20", "2026-09-03")
    scores = {d: dict(sc) for d in cohorts}
    base = {k: (45.0, i + 1) for i, k in enumerate(keys)}      # p000 holds rank 1
    end = {k: (50.0 if i >= 90 else 45.0, i + 1) for i, k in enumerate(keys)}
    board = {"2026-08-19": base, "2026-08-20": base, "2026-09-03": base,
             "2026-09-18": end, "2026-09-19": end, "2026-10-05": end}
    return _make_db(tmp_path / "fx.db", scores, board)


def _null_fixture(tmp_path: Path) -> Path:
    """None scores, a cohort with no matured rows (no end-night rows for its
    players), and every score under the chip threshold (zero flagged rows)."""
    keys = [f"q{i:02d}" for i in range(30)]
    s1 = {k: (None if i % 5 == 0 else 0.01 * i) for i, k in enumerate(keys)}
    scores = {"2026-08-19": s1, "2026-09-01": dict(s1)}
    base = {k: (40.0 + (i % 3) * 5, None if i % 4 == 0 else i) for i, k in enumerate(keys)}
    end = {k: (v[0] + (5.0 if i % 2 else 0.0), v[1])
           for i, (k, v) in enumerate(base.items()) if i < 20}
    board = {"2026-08-19": base, "2026-09-01": base, "2026-09-18": end}
    return _make_db(tmp_path / "nul.db", scores, board)


def test_hit_rule_is_the_template_riser():
    assert lab.HIT_FV_DELTA == 5.0 == HIT_RULES["riser"]["fv_delta"]
    assert lab.is_hit(45.0, 50.0) is True
    assert lab.is_hit(45.0, 49.99) is False
    assert lab.is_hit(None, 50.0) is None and lab.is_hit(45.0, None) is None


def test_top_decile_keeps_every_boundary_tie():
    vals = np.array([0.9, 0.8, 0.8, 0.8] + [0.1] * 16)       # n 20, k 2
    m = lab.top_decile_mask(vals)
    assert m.sum() == 4 and m[:4].all()
    assert lab.top_decile_mask(np.array([])).sum() == 0
    assert lab.top_decile_mask(np.arange(11, dtype=float)).sum() == 2   # ceil(1.1)


def test_monthly_cohorts_take_the_first_date_of_each_month():
    assert lab.monthly_cohorts(["2026-09-03", "2026-08-19", "2026-08-20",
                                "2026-09-04", "2026-10-01"]) == [
        "2026-08-19", "2026-09-03", "2026-10-01"]


def test_maturation_and_base_nights():
    nights = ["2026-08-17", "2026-09-18", "2026-09-20"]
    assert lab.end_night(nights, "2026-08-19", 30) == "2026-09-18"
    assert lab.end_night(nights, "2026-08-25", 30) is None           # not matured
    assert lab.base_night(nights, "2026-08-19") == "2026-08-17"      # 2 days back
    assert lab.base_night(nights, "2026-08-21") is None              # 4 days back


def test_wilson_matches_the_template():
    p, lo, hi = lab._wilson(5, 10)
    assert (p, lo, hi) == (0.5, 0.2366, 0.7634)
    assert lab._rate(0, 0) == {"hits": 0, "n": 0, "rate": None, "ci95": None}


def test_control_b_ranks_by_fv_then_board_rank():
    bb = {"a": (55.0, 9), "b": (60.0, 3), "c": (55.0, 2), "d": (50.0, 1),
          "e": (55.0, None), "f": (45.0, 4), "g": (45.0, 5), "h": (45.0, 6),
          "i": (45.0, 7), "j": (45.0, 8), "k": (45.0, 10)}
    # n 11 (z has no board row), k = ceil(1.1) = 2: b (60), then c (55, rank 2)
    assert lab.fv_top_decile(list(bb) + ["z"], bb) == ["b", "c"]


def test_ladder_words():
    assert lab.ladder(True, True, 5) == "validated for that window"
    assert lab.ladder(True, False, 5) == "repackages consensus FV"
    assert lab.ladder(False, True, 5) == "zero information"
    assert lab.ladder(False, False, 0).startswith("not evaluable")


def test_unmatured_rows_leave_numerator_and_denominator(tmp_path):
    db = _null_fixture(tmp_path)
    archive, _ = lab.load_archive(db)
    nights, board = lab.load_board(db)
    res = lab.evaluate_window(archive, ["2026-08-19"], nights, board, 30,
                              lab.top_decile_mask, (30, 9))
    c = res["cohorts"][0]
    # 24 non-null scores, k 3: q29, q28, q27, none of which has an end-night row
    assert c["archived"] == 24 and c["null_scores"] == 6
    assert c["flagged"] == 3 and c["flagged_scoreable"] == 0
    assert res["badge"]["n"] == 0 and res["ladder"].startswith("not evaluable")
    assert lab.evaluate_window(archive, ["2026-08-19"], nights, board, 60,
                               lab.top_decile_mask, (60, 9))["status"] == "not matured"


def test_both_controls_and_the_validated_verdict(tmp_path):
    db = _validated_fixture(tmp_path)
    out = tmp_path / "eval.json"
    lines: list[str] = []
    doc = lab.run(db, out, today="2026-10-02", head="fixture", emit=lines.append)
    rec = doc["looks"]["30"]["primary"]
    assert rec["cohorts_matured"] == 2                    # 08-19, 09-03 (monthly)
    assert rec["badge"]["rate"] == 1.0 and rec["badge"]["n"] == 20
    assert 0.05 < rec["control_a"]["rate"] < 0.15        # the 10% base rate
    assert rec["control_b"]["rate"] == 0.0
    assert rec["g1_clears_control_a"] and rec["g2_clears_control_b"]
    assert rec["ladder"] == "validated for that window"
    assert doc["looks"]["30"]["daily_sensitivity"]["cohorts_matured"] == 3
    assert doc["seed"] == lab.SEED and doc["as_of"] == "2026-10-02"
    assert set(doc["looks"]) == {"30"}
    assert any("60-day window" in ln for ln in lines)
    assert any(ln == "  window: not matured, no verdict" for ln in lines)
    assert any(ln.startswith("kill rule: not yet evaluable (2 of 6") for ln in lines)
    # seeded: a second fixture run reproduces Control A exactly
    doc2 = lab.run(db, tmp_path / "eval2.json", today="2026-10-02", head="fixture",
                   emit=lambda s: None)
    assert doc2["looks"]["30"]["primary"]["control_a"] == rec["control_a"]


def test_repackages_when_the_score_is_the_fv_column(tmp_path):
    keys = [f"r{i:03d}" for i in range(100)]
    sc = {k: i / 100 for i, k in enumerate(keys)}
    base = {k: (40.0 + i * 0.1, 100 - i) for i, k in enumerate(keys)}
    end = {k: (v[0] + (5.0 if i >= 90 else 0.0), v[1]) for i, (k, v) in enumerate(base.items())}
    db = _make_db(tmp_path / "rp.db", {"2026-08-19": sc},
                  {"2026-08-19": base, "2026-09-18": end})
    doc = lab.run(db, tmp_path / "rp.json", today="2026-10-02", head="fixture",
                  emit=lambda s: None)
    rec = doc["looks"]["30"]["primary"]
    assert rec["g1_clears_control_a"] and not rec["g2_clears_control_b"]
    assert rec["ladder"] == "repackages consensus FV"


def test_refuses_before_the_first_admissible_date_and_on_look_days(tmp_path):
    db = _validated_fixture(tmp_path)
    out = tmp_path / "eval.json"
    with pytest.raises(lab.LabRefusal, match="before the first admissible"):
        lab.run(db, out, today="2026-09-17", head="fixture", emit=lambda s: None)
    with pytest.raises(lab.LabRefusal, match="registered look day"):
        lab.run(db, out, today="2026-11-20", head="fixture", emit=lambda s: None)
    assert not out.exists()


def test_second_30_day_look_is_refused_and_the_artifact_is_unchanged(tmp_path):
    db = _validated_fixture(tmp_path)
    out = tmp_path / "eval.json"
    lab.run(db, out, today="2026-10-02", head="fixture", emit=lambda s: None)
    before = _digest(out)
    with pytest.raises(lab.LabRefusal, match="second write"):
        lab.run(db, out, today="2026-10-03", head="fixture", emit=lambda s: None)
    assert _digest(out) == before
    assert lab.main(["--db", str(db), "--out", str(out)]) == 2
    assert _digest(out) == before


def test_a_later_window_appends_without_touching_the_30_day_record(tmp_path):
    db = _validated_fixture(tmp_path)
    out = tmp_path / "eval.json"
    lab.run(db, out, today="2026-10-02", head="fixture", emit=lambda s: None)
    rec30 = json.loads(out.read_text(encoding="utf-8"))["looks"]["30"]
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO metric_snapshots VALUES (?,?,?,?)",
                    [(f"p{i:03d}", "2026-10-20", i + 1, 45.0) for i in range(100)])
    con.commit()
    con.close()
    lines: list[str] = []
    doc = lab.run(db, out, today="2026-10-20", head="fixture", emit=lines.append)
    assert set(doc["looks"]) == {"30", "60"}
    assert doc["looks"]["30"] == rec30
    assert any("30-day window: recorded in the look of 2026-10-02" in ln for ln in lines)


def test_null_bearing_fixture_runs_the_whole_reporting_path(tmp_path):
    db = _null_fixture(tmp_path)
    out = tmp_path / "nul.json"
    lines: list[str] = []
    doc = lab.run(db, out, today="2026-10-02", head="fixture", emit=lines.append)
    chip = doc["looks"]["30"]["chip_sensitivity"]
    assert chip["flagged_n"] == 0 and chip["badge"]["rate"] is None
    assert chip["control_a"]["rate"] is None
    assert any("n/a (no scoreable rows)" in ln for ln in lines)
    assert all(chr(0x2014) not in ln and chr(0x2013) not in ln for ln in lines)
    json.loads(out.read_text(encoding="utf-8"))


def test_archive_integrity_is_asserted(tmp_path):
    db = _make_db(tmp_path / "dup.db",
                  {"2026-08-19": {"a": 0.5}}, {"2026-08-19": {"a": (45.0, 1)}}, pk=False)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO grpo_score_history VALUES ('2026-08-19', 'a', 0.7)")
    con.commit()
    con.close()
    with pytest.raises(lab.ArchiveIntegrityError):
        lab.load_archive(db)


def test_the_real_artifact_is_never_written_here():
    before = _digest(REAL_OUT)
    assert lab.OUT_PATH == REAL_OUT
    assert _digest(REAL_OUT) == before
