# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the wave 2 anchor arms (efv_w2_anchor.py, EFV3_W2_1c). Synthetic rows only:
no frame, no label module and no served artifact is read here.

1. Leakage: the AN-1 and AN-2 weights for vintage V read no row after V - 3 (a later
   label moved anywhere leaves every weight unchanged); the AN-2 scheme is decided by
   counts, not outcomes; a listing dated after the read never sets a row's group.
2. The anchor column: equal per-row weights give efv_v2_candidates.anchor_values bit for
   bit; a missing source renormalizes over the present ones; a row with no source takes
   the consensus percentile and is counted; coverage per year and side.
3. The fixed variant is 2 to 1 Pipeline everywhere; AN-2 shrinks toward the AN-1 weights.
4. Position groups: the fine and C02 maps; pitchers sp and rp; no listing reads unknown.
5. Guards: a reserved list vintage or a 2025+ year raises before any weight is built.
6. The lab registers the arms; no FV-level grouping token; no em-dash.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_v2_candidates as C
import efv_vintage_frame as F
import efv_w2_anchor as A

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "efv_w2_anchor.py"
sys.path.insert(0, str(ROOT / "tools"))

SINGLE = {"k": 1.0, "prior": 40.0}
SRCS = ("fangraphs", "mlb_pipeline")


def _hist_rows(rng, n, *, fg_from=2011, groups=("middle", "corner", "other"), noise=1.0):
    """{V: rows} with both sources' grades, a target and a group; FanGraphs grades only
    from `fg_from`. The Pipeline grade tracks the target more closely than FanGraphs."""
    out = {}
    for V in range(2011, 2020):
        rows = []
        for i in range(n):
            t = float(rng.normal())
            g = {"mlb_pipeline": 45 + 5 * (t + 0.5 * float(rng.normal()))}
            if V >= fg_from:
                g["fangraphs"] = 45 + 5 * (t + noise * 2.0 * float(rng.normal()))
            grp = groups[i % len(groups)]
            rows.append({"grades": g, "target": t, "group": {"fine": grp, "c02": grp}})
        out[V] = rows
    return out


def _rel(by_side, frame="lv"):
    return C.build_source_reliability(by_side, single_source=SINGLE, sources=SRCS,
                                      frame=frame)


# 1. leakage --------------------------------------------------------------------

def test_weights_for_v_read_nothing_after_v_minus_3():
    rng = np.random.default_rng(1)
    by = {"hit": _hist_rows(rng, 120)}
    rel = _rel(by)
    grp = A.group_reliability(by, rel, frame="lv")
    moved = {"hit": {V: [dict(r, target=(-r["target"] if V >= 2017 else r["target"]))
                         for r in rows] for V, rows in by["hit"].items()}}
    rel2 = _rel(moved)
    grp2 = A.group_reliability(moved, rel2, frame="lv")
    for V in ("2014", "2015", "2016", "2017", "2018", "2019"):
        assert rel["table"]["hit"][V] == rel2["table"]["hit"][V]
        assert grp["table"]["hit"][V]["groups"] == grp2["table"]["hit"][V]["groups"]
        assert max(grp["table"]["hit"][V]["reads"]) <= int(V) - 3
    # a change at or before V - 3 can move the V weights (the read is live)
    early = {"hit": {V: [dict(r, target=(-r["target"] if V == 2013 else r["target"]))
                         for r in rows] for V, rows in by["hit"].items()}}
    assert _rel(early)["table"]["hit"]["2016"] != rel["table"]["hit"]["2016"]


def test_scheme_is_decided_by_counts_only():
    rng = np.random.default_rng(2)
    fine = A.HIT_FINE_GROUPS
    rows = _hist_rows(rng, 6 * 120, groups=fine)
    for rr in rows.values():
        for r in rr:
            r["group"]["c02"] = "other"
    by = {"hit": rows}
    rel = _rel(by)
    t = A.group_reliability(by, rel, frame="lv")["table"]["hit"]
    # 2019 reads 2011..2016: 6 x 120 = 720 rows per fine group, above the floor
    assert t["2019"]["scheme"] == "fine"
    # 2014 reads 2011 only: 120 rows per fine group, below it, so the C02 families
    assert t["2014"]["scheme"] == "c02"
    flipped = {"hit": {V: [dict(r, target=-r["target"]) for r in rr] for V, rr in rows.items()}}
    t2 = A.group_reliability(flipped, _rel(flipped), frame="lv")["table"]["hit"]
    assert {V: e["scheme"] for V, e in t.items()} == {V: e["scheme"] for V, e in t2.items()}


def test_a_listing_after_the_read_never_sets_the_group():
    import efv_v2_pricing_calibration as PC

    class NoRoles:
        def role(self, mlbam, read_date):
            return None
    listings = {"p1": [("2016-05-01", "mlb_pipeline", "SS"),
                       ("2017-06-01", "mlb_pipeline", "1B")]}
    cov = PC.covariates("hit", player_key="p1", mlbam=None, birth_date=None,
                        read_date="2017-03-01", lo="2016-03-01", hi="2017-03-02",
                        listings=listings, roles=NoRoles())
    assert A.row_groups("hit", cov)["fine"] == "SS"
    cov2 = PC.covariates("hit", player_key="p1", mlbam=None, birth_date=None,
                         read_date="2016-03-01", lo="2015-03-01", hi="2016-03-02",
                         listings=listings, roles=NoRoles())
    assert A.row_groups("hit", cov2)["fine"] == A.UNKNOWN


# 2. the anchor column -------------------------------------------------------------

def _frame_rows(rng, n, V=2017):
    rows = []
    for i in range(n):
        g = {}
        if i % 5 != 0:
            g["mlb_pipeline"] = float(rng.integers(35, 61))
        if i % 3 != 0:
            g["fangraphs"] = float(rng.integers(35, 61))
        rows.append({"player_key": f"p{i}", "decision_year": V, "grades": g,
                     "fv": float(rng.integers(35, 61))})
    return rows


def test_equal_weights_reproduce_mc2_anchor_values():
    rng = np.random.default_rng(3)
    rows = _frame_rows(rng, 60) + _frame_rows(rng, 40, V=2018)
    rel = {"table": {"hit": {"2017": {"fangraphs": 0.8, "mlb_pipeline": 1.3},
                             "2018": {"fangraphs": 1.0, "mlb_pipeline": 1.0}}},
           "sources": {"hit": list(SRCS)}, "single_source": SINGLE}
    u_ref, miss_ref = C.anchor_values(rows, rel, "hit")
    w = A.row_weights(rows, "hit", rel)
    u, miss = A.anchor_column(rows, w, SRCS, SINGLE)
    assert np.array_equal(u, u_ref) and miss == miss_ref


def test_missing_source_renormalizes_and_none_falls_back():
    rows = [{"player_key": "a", "decision_year": 2017, "fv": 50.0,
             "grades": {"mlb_pipeline": 55.0, "fangraphs": 50.0}},
            {"player_key": "b", "decision_year": 2017, "fv": 45.0,
             "grades": {"mlb_pipeline": 45.0}},
            {"player_key": "c", "decision_year": 2017, "fv": 40.0,
             "grades": {"mlb_pipeline": 50.0, "fangraphs": 55.0}},
            {"player_key": "d", "decision_year": 2017, "fv": 35.0, "grades": {}}]
    lo = [{"mlb_pipeline": 1.0, "fangraphs": 0.1}] * 4
    hi = [{"mlb_pipeline": 1.0, "fangraphs": 9.0}] * 4
    u_lo, miss = A.anchor_column(rows, lo, SRCS, SINGLE)
    u_hi, _ = A.anchor_column(rows, hi, SRCS, SINGLE)
    # row b carries Pipeline alone: its anchor ignores the FanGraphs weight entirely
    assert u_lo[1] == u_hi[1]
    assert miss == 1
    cons = C.H.within_pct([r["fv"] for r in rows], [2017] * 4)
    assert u_lo[3] == cons[3]
    cov = A.coverage(rows, "hit")["by_year"]["2017"]
    assert cov == {"n": 4, "by_source": {"fangraphs": 2, "mlb_pipeline": 3}, "both": 2,
                   "single": 1, "none": 1}


# 3. the variants ----------------------------------------------------------------

def test_fixed_variant_is_two_to_one_everywhere():
    rng = np.random.default_rng(4)
    rel = _rel({"hit": _hist_rows(rng, 60), "pit": _hist_rows(rng, 60)})
    fx = A.fixed_reliability(rel)
    for side in ("hit", "pit"):
        for V, w in fx["table"][side].items():
            assert w == {"fangraphs": 1.0, "mlb_pipeline": 2.0}, (side, V)


def test_an2_shrinks_toward_an1_and_lone_history_takes_global():
    rng = np.random.default_rng(5)
    by = {"hit": _hist_rows(rng, 300)}
    rel = _rel(by)
    t = A.group_reliability(by, rel, frame="lv")["table"]["hit"]["2019"]
    for g, w in t["groups"].items():
        # Pipeline tracks the target better in every group: weighted up, inside the clamp
        assert w["mlb_pipeline"] > w["fangraphs"], g
        assert 0.6 <= w["fangraphs"] <= 1.5 and 0.6 <= w["mlb_pipeline"] <= 1.5
    # FanGraphs only from 2017: no group has two sources with history at V - 3, so
    # every group carries the global weights (here both 1.0)
    late = {"hit": _hist_rows(np.random.default_rng(6), 300, fg_from=2017)}
    rel_l = _rel(late)
    t_l = A.group_reliability(late, rel_l, frame="lv")["table"]["hit"]["2019"]
    for g, w in t_l["groups"].items():
        assert w == rel_l["table"]["hit"]["2019"] == {"fangraphs": 1.0, "mlb_pipeline": 1.0}


def test_row_weights_use_the_group_of_the_row_and_global_without_one():
    rel = {"table": {"hit": {"2017": {"fangraphs": 0.9, "mlb_pipeline": 1.2}}},
           "sources": {"hit": list(SRCS)}}
    gt = {"table": {"hit": {"2017": {"scheme": "c02", "key": "c02",
                                     "groups": {"middle": {"fangraphs": 0.7,
                                                           "mlb_pipeline": 1.4}}}}}}
    rows = [{"player_key": "a", "decision_year": 2017},
            {"player_key": "b", "decision_year": 2017}]
    groups = {("a", 2017): {"fine": "SS", "c02": "middle"}}
    w = A.row_weights(rows, "hit", rel, groups=groups, group_table=gt)
    assert w[0] == {"fangraphs": 0.7, "mlb_pipeline": 1.4}
    assert w[1] == {"fangraphs": 0.9, "mlb_pipeline": 1.2}


# 4. groups ------------------------------------------------------------------------

@pytest.mark.parametrize("pos,fine,c02", [("SS/2B", "SS", "middle"), ("C", "C", "middle"),
                                          ("CF", "CF", "middle"), ("2B", "IF", "other"),
                                          ("3B", "IF", "other"), ("LF", "COF", "corner"),
                                          ("OF", "COF", "other"), ("1B", "1B_DH", "corner"),
                                          ("DH", "1B_DH", "corner"), ("UT", "unknown", "other")])
def test_hitter_groups(pos, fine, c02):
    g = A.row_groups("hit", {"listing": {"position": pos}, "family_how": "listing"})
    assert (g["fine"], g["c02"]) == (fine, c02)


def test_pitcher_groups_and_unknown():
    assert A.row_groups("pit", {"family": "rp", "family_how": "milb_gs_share"})["fine"] == "rp"
    assert A.row_groups("pit", {"family": None, "family_how": "none"})["fine"] == A.UNKNOWN
    assert A.row_groups("hit", {"listing": None, "family_how": "none"})["fine"] == A.UNKNOWN
    assert A.row_groups("hit", None)["c02"] == A.UNKNOWN


# 5. guards ------------------------------------------------------------------------

def test_a_reserved_vintage_raises():
    rng = np.random.default_rng(7)
    rows = _hist_rows(rng, 30)
    rel = _rel({"hit": rows})
    bad = dict(rows)
    bad[2020] = rows[2019]
    with pytest.raises(F.ReservedFrameError):
        A.group_reliability({"hit": bad}, rel, frame="lv")
    with pytest.raises(F.ReservedFrameError):
        A.group_reliability({"hit": rows}, rel, target_vintages=[2025], frame="vm")


# 6. registration and source scans ---------------------------------------------------

def test_the_lab_registers_the_arms():
    import efv_screen_lab as LAB
    assert LAB.WAVE2_DEV[A.MODULE] == A.ARMS
    assert A.OUT_PATH.as_posix().endswith("data/_labs/efv_w2/efv_w2_anchor.json")
    assert set(A.ARM_IDS.values()) == {f"efv_w2_anchor:{a}" for a in A.ARMS}


def test_a_tilted_read_lands_no_progress_row():
    f = {"n": 1, "raters": {}, "deltas": {}, "verdict": "v", "note": "n"}
    doc = {"generated_at": "g", "arms": {"an1_pl": {"model_id": "efv_w2_anchor:an1_pl",
                                                     "frames": {"lv_dev": dict(f, tilted=True),
                                                                "vm_dev": dict(f)}}}}
    (d,) = A.progress_docs(doc)
    assert list(d["frames"]) == ["vm_dev"] and d["role"] == "development"


_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")


def test_no_fv_level_grouping_and_no_dash():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED_TOKENS), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value
    for p in (SRC, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt
