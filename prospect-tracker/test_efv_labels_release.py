# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_10 pins (docs/efv-v2/SURROGATE_2026_GATE.md s6.3, amendment dated 2026-10-19): the
release path of efv_labels.labels_for.

1. A synthetic reserved row stays reserved_vm with no record (and with the wrong
   record) and reads released_vm, with W3, W2 and R3, with its cohort's record.
2. A 2025 debutant never gets an L6, released or not (2025 is in DEBUT_YEARS).
3. The cohort map equals the surrogate guard's; unknown record ids raise.
4. The look runner's long_run_labels refuses before any label is built without the
   records, and passes them when the guard opens.
5. The DS-03 pattern: no module but efv_labels.py itself and the look runner passes
   release_records; efv_v2_model._check_years and every served path never see it.

Every row is synthetic. Nothing here reads a real outcome or a real reserved row.
"""
from __future__ import annotations

import ast
import inspect
import re
import subprocess
import warnings
from pathlib import Path

import pytest

import efv_dataset as D
import efv_labels as L
import efv_surrogate_guard as G
import efv_v2_model as M
import efv_vintage_frame as F
from tools import efv_surrogate_look as K

ROOT = Path(__file__).parent


def _rec(key, debut):
    return {"player_key": key, "debut_date": debut, "position": "SS", "mlbam_id": None,
            "birth_date": "2003-03-01", "points": [], "statline": {}}


@pytest.fixture
def rt_2031(monkeypatch):
    monkeypatch.setattr(D, "RESOLVED_THROUGH", 2031)


SEASONS_25 = {2025: 1.0, 2026: 2.0, 2027: 3.0, 2028: 9.0}


# ---------------------------------------------------------------------------
# 1 and 2. reserved, released, never an L6
# ---------------------------------------------------------------------------

def test_reserved_row_stays_reserved_without_its_record(rt_2031):
    rec = _rec("syn_2025", "2025-05-01")
    for recs in (None, (), ("rvm_look_2",), ("rvm_look_3", "oq6_release")):
        lab = L.labels_for(rec, 2024, SEASONS_25, release_records=recs)
        assert lab["status"] == "reserved_vm", recs
        assert lab["w3"] is None and lab["w2"] is None and lab["l6"] is None
    assert L.labels_for(rec, 2024, SEASONS_25) == \
        L.labels_for(rec, 2024, SEASONS_25, release_records=None)


def test_reserved_row_reads_released_with_its_record(rt_2031):
    rec = _rec("syn_2025", "2025-05-01")
    lab = L.labels_for(rec, 2024, SEASONS_25, release_records={"rvm_look_1"})
    assert lab["status"] == L.RELEASED_VM == "released_vm"
    assert lab["debut_year"] == 2025
    assert lab["w3"] == 6.0 and lab["w3_debut"] is True
    assert lab["w2"] == 3.0 and lab["w2_debut"] is True
    assert lab["r3"] == 1.0
    assert lab["l6"] is None and lab["l6_censored_target"] is None
    assert lab["l6_weight"] is None and lab["l6_censored"] is None


def test_the_oq6_cohorts_release_only_on_the_oq6_record(rt_2031):
    rec = _rec("syn_2028", "2028-05-01")
    s = {2028: 1.0, 2029: 1.0, 2030: 1.0}
    assert L.labels_for(rec, 2026, s, release_records={"rvm_look_1", "rvm_look_2",
                                                       "rvm_look_3"})["status"] == \
        "reserved_vm"
    lab = L.labels_for(rec, 2026, s, release_records={"oq6_release"})
    assert lab["status"] == "released_vm" and lab["w3"] == 3.0 and lab["r3"] == 1.0
    assert lab["l6"] is None


def test_a_2025_debutant_never_gets_an_l6():
    assert 2025 in D.DEBUT_YEARS        # the reason the test exists
    rec = _rec("syn_2025", "2025-05-01")
    for recs in (None, set(L.RELEASE_RECORD_BY_COHORT.values())):
        lab = L.labels_for(rec, 2024, SEASONS_25, release_records=recs)
        assert lab["l6"] is None and lab["l6_weight"] is None, recs


def test_a_non_reserved_row_is_unchanged_by_any_record(rt_2031):
    rec = _rec("syn_2017", "2017-05-01")
    s = {2017: 1.0, 2018: 2.0, 2019: 3.0}
    base = L.labels_for(rec, 2015, s)
    assert base["status"] == "ok" and base["l6"] is not None
    assert L.labels_for(rec, 2015, s,
                        release_records=set(L.RELEASE_RECORD_BY_COHORT.values())) == base


# ---------------------------------------------------------------------------
# 3. the cohort map and the record ids
# ---------------------------------------------------------------------------

def test_cohort_map_equals_the_guard():
    assert L.RELEASE_RECORD_BY_COHORT == G.COHORT_RELEASE
    assert set(L.RELEASE_RECORD_BY_COHORT.values()) == set(G.RECORD_IDS)
    assert G.DEBUT_WINDOW_SEASONS["lv2026_long_run"] == L.W_DEBUT_WINDOW
    assert min(L.RELEASE_RECORD_BY_COHORT) == F.R_VM_FIRST_DEBUT_YEAR


def test_unknown_record_ids_raise():
    with pytest.raises(ValueError, match="unknown release record"):
        L.labels_for(_rec("syn", "2025-05-01"), 2024, SEASONS_25,
                     release_records={"rvm_look_9"})


# ---------------------------------------------------------------------------
# 4. the runner's long-run label path
# ---------------------------------------------------------------------------

def test_long_run_labels_refuses_before_any_label(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a label was built before the guard opened")
    monkeypatch.setattr(L, "labels_for_frame", boom)
    with pytest.raises(F.ReservedFrameError):
        K.long_run_labels([{"player_key": "syn", "vintage": 2026}], gate_sha=None,
                          look_records=())


def test_long_run_labels_releases_with_every_record(monkeypatch, rt_2031):
    allrec = frozenset(G.RECORD_IDS)
    seen = []
    monkeypatch.setattr(G, "guard_surrogate_read",
                        lambda V, **k: seen.append((V, k["purpose"])))
    monkeypatch.setattr(G, "look_records", lambda: allrec)
    uni = {"a": _rec("a", "2027-05-01"), "b": _rec("b", "2029-05-01")}
    war = {"a": {2027: 1.0, 2028: 1.0, 2029: 1.0}, "b": {2029: 2.0}}
    rows = [{"player_key": k, "vintage": 2026} for k in uni]
    labs = K.long_run_labels(rows, gate_sha="0" * 40, look_records=allrec,
                             universe=uni, war=war)
    assert seen == [(2026, "lv2026_long_run")]
    assert [lb["status"] for lb in labs] == ["released_vm", "released_vm"]
    assert labs[0]["w3"] == 3.0 and all(lb["l6"] is None for lb in labs)


# ---------------------------------------------------------------------------
# 5. the DS-03 pattern: who may pass release_records
# ---------------------------------------------------------------------------

ALLOWED_CALLERS = {"efv_labels.py", "tools/efv_surrogate_look.py",
                   "test_efv_labels_release.py"}


def _tracked_py() -> list[str]:
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.py"],
                       capture_output=True, text=True, check=True)
    return [p for p in r.stdout.splitlines() if p]


def _callers(rel: str) -> list[tuple[str, int]]:
    try:
        text = (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if "release_records" not in text:     # no call can pass the keyword
        return []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(text)
    parent = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parent[ch] = node
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and any(k.arg == "release_records" for k in n.keywords):
            p = parent.get(n)
            while p is not None and not isinstance(p, (ast.FunctionDef,
                                                       ast.AsyncFunctionDef)):
                p = parent.get(p)
            out.append((p.name if p is not None else "<module>", n.lineno))
    return out


def test_only_the_long_run_runner_passes_release_records():
    files = _tracked_py()
    assert "efv_labels.py" in files and "tools/efv_surrogate_look.py" in files
    bad = {}
    for rel in files:
        hits = _callers(rel)
        if hits and rel not in ALLOWED_CALLERS:
            bad[rel] = hits
    assert not bad, bad
    runner = {name for name, _ in _callers("tools/efv_surrogate_look.py")}
    assert runner == {"long_run_labels"}, runner
    assert K.LONG_RUN_PURPOSE == "lv2026_long_run"
    src = inspect.getsource(K.long_run_labels)
    assert "purpose=LONG_RUN_PURPOSE" in src and not re.search(r"(?<!_)\bPURPOSE\b", src)
    labels_internal = {name for name, _ in _callers("efv_labels.py")}
    assert labels_internal == {"labels_for_frame"}, labels_internal


def test_served_paths_never_see_a_release():
    assert "release" not in inspect.getsource(M._check_years)
    for rel in _tracked_py():
        if rel in ALLOWED_CALLERS:
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        assert "released_vm" not in text and "release_records" not in text, rel
