# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/efv_beat_pooled_power.py (EFV_BEAT_POOLED_POWER, docs/efv-v2/EFV_BEAT_POOLED_POWER.md):
the registered constants, the de-duplication rule, the statistic against efv_v2_stat, the club
rule, the pass rule, the anchor-gate scan and the artifact's own consistency."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_beat_pooled_power as P  # noqa: E402
import efv_v2_stat as S  # noqa: E402


def _row(key, kind, side, year, scores, y, club="AAA"):
    fid = "lv_dev" if kind == "lv" else "vm_dev"
    return {"key": key, "frame": fid, "kind": kind, "side": side, "year": year,
            "pgroup": f"{fid}:{side}|{year}", "club": club, "scores": scores, "y": y}


def _synthetic(seed=3, n_groups=6, per=40):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_groups):
        side = "hit" if g % 2 else "pit"
        kind = "lv" if g < 4 else "vm"
        for i in range(per):
            y = float(rng.normal())
            sc = {k: y + float(rng.normal()) * 2 for k in (P.V5, P.V2, P.V1, P.CONS)}
            rows.append(_row(f"p{g}_{i % 30}", kind, side, 2017 + g, sc, y, club=f"c{i % 7}"))
    return rows


def test_the_registered_constants():
    assert P.B == 4000 and P.SEED == 20261016
    assert P.PRIMARY == "v5c_vs_consensus" and P.COMPARISONS[0] == (P.PRIMARY, P.V5, P.CONS)
    assert P.DEDUP_PRIMARY == "keep_lv" and P.DEDUP_RULES[0] == "keep_lv"
    assert P.CLUSTERINGS == ("player", "club")
    assert P.GATE_SHA == "e7931ce4e13110eebb53555bff455ff13ca7c502"
    assert P.REGISTRATION_COMMIT == "4eee1808"
    assert (ROOT / P.DOC).exists()


def test_dedupe_keeps_the_lv_rows_of_a_player_in_both_frames():
    sc = {P.V5: 1.0, P.V2: 1.0, P.V1: 1.0, P.CONS: 1.0}
    rows = [_row("a", "lv", "hit", 2017, sc, 0.0), _row("a", "lv", "hit", 2018, sc, 0.0),
            _row("a", "vm", "hit", 2020, sc, 0.0), _row("b", "vm", "hit", 2021, sc, 0.0),
            _row("c", "lv", "pit", 2019, sc, 0.0)]
    keep_lv = P.dedupe(rows, "keep_lv")
    assert [(r["key"], r["kind"]) for r in keep_lv] == [("a", "lv"), ("a", "lv"), ("b", "vm"),
                                                        ("c", "lv")]
    keep_vm = P.dedupe(rows, "keep_vm")
    assert [(r["key"], r["kind"]) for r in keep_vm] == [("a", "vm"), ("b", "vm"), ("c", "lv")]
    assert len(P.dedupe(rows, "none")) == 5
    with pytest.raises(ValueError):
        P.dedupe(rows, "keep_both")


def test_the_pooled_statistic_is_efv_v2_stat_within_pair_over_frame_groups():
    rows = _synthetic()
    pool = P.Pool(rows, (P.V5, P.CONS))
    idx = np.arange(pool.n)
    ta, tb = S._within_pair(pool.score[P.V5], pool.score[P.CONS], pool.y, pool.codes,
                            pool.keep, idx)
    wa, wb = pool.pair(pool.group_rhos(idx), P.V5, P.CONS, "both")
    assert wa == pytest.approx(ta, abs=1e-12) and wb == pytest.approx(tb, abs=1e-12)
    # a drawn index with repeats too
    rng = np.random.default_rng(7)
    draw = rng.integers(0, pool.n, pool.n)
    ta, tb = S._within_pair(pool.score[P.V5], pool.score[P.CONS], pool.y, pool.codes,
                            pool.keep, draw)
    wa, wb = pool.pair(pool.group_rhos(draw), P.V5, P.CONS, "both")
    assert wa == pytest.approx(ta, abs=1e-12) and wb == pytest.approx(tb, abs=1e-12)


def test_frames_never_share_a_group_code():
    sc = {P.V5: 1.0, P.V2: 1.0, P.V1: 1.0, P.CONS: 1.0}
    a = _row("a", "lv", "hit", 2018, sc, 0.0)
    b = _row("b", "vm", "hit", 2018, sc, 0.0)
    assert a["pgroup"] != b["pgroup"]


def test_read_pool_reports_power_and_both_clusterings():
    out = P.read_pool(_synthetic(), P.COMPARISONS[:1], B_=120, seed=5, log=lambda *_: None)
    leg = out["legs"]["v5c_vs_consensus|both"]
    for cl in P.CLUSTERINGS:
        blk = leg[cl]
        assert blk["status"] == "derived" and blk["B"] == 120
        assert blk["ci95"][0] <= blk["lb95"] <= blk["ub95"] <= blk["ci95"][1]
        assert blk["mde95"] == pytest.approx(1.645 * blk["sd"], abs=1e-3)
    sides = out["legs"]["v5c_vs_consensus|hit"]["n"] + out["legs"]["v5c_vs_consensus|pit"]["n"]
    assert sides == leg["n"]


def test_club_rule():
    rec = {"points": [{"snapshot_date": "2016-07-01", "org": "nyy"},
                      {"snapshot_date": "2017-02-01", "org": "BOS"},
                      {"snapshot_date": "2017-03-01", "org": ""},
                      {"snapshot_date": "2017-06-01", "org": "SEA"}]}
    assert P.club_of(rec, 2017) == "BOS"
    assert P.club_of(rec, 2016) == P.CLUB_UNKNOWN
    assert P.club_of({"points": [{"snapshot_date": "2016-07-01", "org": "nyy"}]}, 2017) == "NYY"
    assert P.club_of(None, 2017) == P.CLUB_UNKNOWN


@pytest.mark.parametrize("lp,lc,ub,want", [(0.001, 0.002, 0.03, ("PASS", "beats")),
                                           (0.001, -0.001, 0.03, ("FAIL", "ties")),
                                           (-0.03, -0.03, 0.01, ("FAIL", "ties")),
                                           (-0.05, -0.05, -0.001, ("FAIL", "trails"))])
def test_the_pass_rule(lp, lc, ub, want):
    v = P.verdict({"delta": 0.0, "player": {"lb95": lp, "ub95": ub}, "club": {"lb95": lc}})
    assert (v["verdict"], v["word"]) == want
    assert v["pass"] is (want[0] == "PASS")


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = (ROOT / P.TOOL).read_text(encoding="utf-8")
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert bad not in src
    for path in (ROOT / P.TOOL, ROOT / P.DOC, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_artifact_is_consistent_with_the_registered_rule():
    if not P.OUT_PATH.exists():
        pytest.skip("the read has not run")
    doc = json.loads(P.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["item"] == P.ITEM and doc["bootstrap"]["B"] == 4000
    assert doc["bootstrap"]["seed"] == 20261016
    leg = doc["pooled"]["legs"]["v5c_vs_consensus|both"]
    assert P.verdict(leg) == doc["verdict"]
    assert doc["power_first"]["mde95_player"] == leg["player"]["mde95"]
    assert set(doc["pooled"]["n_by_frame"]) <= {"lv_dev", "vm_dev"}
    for g in doc["pooled"]["groups_kept"]:
        frame, rest = g.split(":", 1)
        side, year = rest.split("|")
        assert frame in ("lv_dev", "vm_dev") and side in ("hit", "pit")
        assert int(year) < 2025
        assert not (frame == "lv_dev" and int(year) in (2020, 2021))
    for fid, rec in doc["parity"].items():
        assert all(v["ok"] for k, v in rec.items() if k != "n")
    if doc.get("spent") is not None:
        sp = doc["spent"]
        assert sp["label"].startswith("SPENT")
        assert set(sp["pooled"]["n_by_frame"]) <= {"lv_res", "vm_pros"}
        assert P.verdict(sp["pooled"]["legs"]["v5c_vs_consensus|both"]) == sp["reading"]
