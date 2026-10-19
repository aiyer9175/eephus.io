# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/efv_beat_tilted_labels.py (EFV_BEAT_TILTED_LABELS, docs/efv-v2/EFV_BEAT_TILTED_LABELS.md):
the registered constants, the labels, the AUC statistic, the pass rule, the anchor-gate scan,
the registration-first order and the artifact's own consistency."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_beat_pooled_power as PP  # noqa: E402
import efv_beat_tilted_labels as T  # noqa: E402


def test_the_registered_constants():
    assert T.B == 2000 and T.SEED == 20261017
    assert T.CLUSTERINGS == ("player", "club")
    assert T.COMPARISONS[0] == (T.DECIDING, T.SERVED, T.CONS)
    assert T.CLAIMS[T.PRIMARY] == {"lv_dev": "R3", "vm_dev": "AD"}
    assert T.LABELS == {"lv_dev": ("R3", "R5", "W2"), "vm_dev": ("AD", "W2")}
    assert T.FRAMES == ("lv_dev", "vm_dev")
    assert T.N_PERM == 200 and T.B_PLANT == 500 and T.PLANT_A == 0.15
    assert (ROOT / T.DOC).exists()


def test_the_registration_was_committed_alone_before_the_module():
    r = subprocess.run(["git", "show", "--name-only", "--format=", T.REGISTRATION_COMMIT],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("registration commit not in this clone")
    files = [f for f in r.stdout.split() if f.strip()]
    assert files == ["prospect-tracker/" + T.DOC]


def test_r5_label():
    lab = {"vintage": 2018, "reached": "reached", "debut_year": 2023, "r3": 0.0,
           "status": "ok"}
    assert T.r5_label(lab) == 1.0
    assert T.r5_label(dict(lab, debut_year=2024)) == 0.0
    assert T.r5_label(dict(lab, reached="never", debut_year=None)) == 0.0
    assert T.r5_label(dict(lab, reached="censored_never", debut_year=None)) == 0.0
    assert T.r5_label(dict(lab, status="identity_conflict", r3=None)) is None


def test_arrival_day_orientation_and_guards():
    early = T.arrival_day("2019-03-28", 2019, False)
    late = T.arrival_day("2019-09-01", 2019, False)
    assert early > late and early == -86.0
    assert T.arrival_day("2019-07-01", 2019, True) is None
    assert T.arrival_day("2020-04-01", 2019, False) is None
    assert T.arrival_day("2019", 2019, False) is None
    assert T.arrival_day(None, 2019, False) is None


def test_early_war_reads_two_seasons_from_the_debut():
    s = {2018: 0.5, 2019: 1.25, 2020: 4.0}
    assert T.early_war(s, 2018) == 1.75
    assert T.early_war(s, 2020) == 4.0
    assert T.early_war(None, 2020) == 0.0


def _rows(seed=4, per=60):
    rng = np.random.default_rng(seed)
    out = []
    for g, (side, year) in enumerate((("hit", 2017), ("pit", 2017), ("hit", 2018))):
        for i in range(per):
            y = float(rng.random() < 0.4)
            sc = {k: y * 0.5 + float(rng.normal()) for k in (T.SERVED, T.CONS)}
            out.append({"key": f"p{g}_{i}", "frame": "lv_dev", "kind": "lv", "side": side,
                        "year": year, "pgroup": f"lv_dev:{side}|{year}", "club": f"c{i % 5}",
                        "y": y, "scores": sc})
    return out


def test_auc_matches_the_mann_whitney_definition():
    rows = _rows()
    out = T.read_auc(rows, (("x", T.SERVED, T.CONS),), B_=60, seed=3)
    pool = PP.Pool(rows, (T.SERVED, T.CONS))
    tot = n = 0.0
    for u in pool.keep:
        m = pool.codes == u
        s, y = pool.score[T.SERVED][m], pool.y[m]
        pos, neg = s[y > 0.5], s[y < 0.5]
        auc = np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg])
        tot += auc * m.sum()
        n += m.sum()
    assert out["raters"][T.SERVED] == pytest.approx(tot / n, abs=1e-4)
    for cl in T.CLUSTERINGS:
        assert out["legs"]["x"][cl]["status"] == "derived"


@pytest.mark.parametrize("lp,lc,ub,want", [(0.001, 0.002, 0.03, (True, "beats")),
                                           (0.001, -0.001, 0.03, (False, "ties")),
                                           (-0.05, -0.05, -0.001, (False, "trails"))])
def test_frame_verdict(lp, lc, ub, want):
    v = T.frame_verdict({"delta": 0.0, "n": 10, "player": {"lb95": lp, "ub95": ub},
                         "club": {"lb95": lc}})
    assert (v["lb_above_0"], v["word"]) == want


def test_the_claim_needs_both_frames_the_null_and_the_planted_check():
    ok = {"lb_above_0": True, "word": "beats"}
    no = {"lb_above_0": False, "word": "ties"}
    null_ok = {f: {"above_null_p95": True} for f in T.FRAMES}
    plant_ok = {f: {"recovered": True} for f in T.FRAMES}
    both = {f: ok for f in T.FRAMES}
    assert T.claim_verdict(both, null_ok, plant_ok)["pass"] is True
    assert T.claim_verdict({"lv_dev": ok, "vm_dev": no}, null_ok, plant_ok)["pass"] is False
    assert T.claim_verdict(both, dict(null_ok, vm_dev={"above_null_p95": False}),
                           plant_ok)["pass"] is False
    v = T.claim_verdict(both, null_ok, dict(plant_ok, lv_dev={"recovered": False}))
    assert v["pass"] is False and v["words"]["lv_dev"] == "unresolved"


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = (ROOT / T.TOOL).read_text(encoding="utf-8")
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum",
                "run_backtest", "train_proj_models"):
        assert bad not in src
    for path in (ROOT / T.TOOL, ROOT / T.DOC, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text


def test_the_artifact_is_consistent_with_the_registered_rule():
    if not T.OUT_PATH.exists():
        pytest.skip("the read has not run")
    doc = json.loads(T.OUT_PATH.read_text(encoding="utf-8"))
    assert doc["item"] == T.ITEM and doc["bootstrap"]["B"] == T.B
    assert doc["bootstrap"]["seed"] == T.SEED and doc["label"]["provider"] == "fwar"
    for claim, c in doc["claims"].items():
        per = {}
        for fid in T.FRAMES:
            leg = doc["reads"][f"{fid}|{c['labels'][fid]}"]["legs"][f"{T.DECIDING}|both"]
            per[fid] = T.frame_verdict(leg)
            assert per[fid] == c["served"][fid]
        prim = claim == T.PRIMARY
        assert T.claim_verdict(per, doc["null"] if prim else None,
                               doc["planted"] if prim else None) == c["reading"]
    assert doc["verdict"] == doc["claims"][T.PRIMARY]["reading"]
    for key in doc["reads"]:
        fid, label = key.split("|")
        assert label in T.LABELS[fid]
        for g in doc["reads"][key]["groups_kept"]:
            frame, rest = g.split(":", 1)
            side, year = rest.split("|")
            assert frame == fid and side in ("hit", "pit") and int(year) < 2025
            assert int(year) not in (2020, 2021) or frame == "vm_dev"
    for fid, rec in doc["receipts"]["parity"].items():
        assert abs(rec["v5c_dev"]["recomputed"] - rec["v5c_dev"]["committed"]) <= T.PARITY_TOL_V5
        assert abs(rec["rt_as_read"]["recomputed"]
                   - rec["rt_as_read"]["committed"]) <= T.PARITY_TOL_RT
    if not doc["verdict"]["pass"]:
        assert doc["spent"] == "not opened"
