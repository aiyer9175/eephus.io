# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the Library's "What Predicts the Majors" view (EFV5_ATLAS_PAGE) and its
payload, data/efv5_metric_atlas_view.json (efv5_atlas_view.py).

1. Served invariants on the payload: every number is the atlas's own (re-read from the
   atlas's cells file), the raw score reads at or above the no-relation line, intervals
   bracket their points, q is a probability, no scored row sits under the declared
   minimum, nothing is keyed or named by a consensus-FV level, no em-dash.
2. Freshness: the payload names the atlas file it was built from by sha256.
3. The chip is derived, never typed: the admitted rows are exactly the driver
   selection's chosen columns and the tracking head's weight-carrying metrics, and
   nothing reads "live" while the served switches are off.
4. The page: the view is registered, fetches the payload, carries the explainer and
   hides cells under the minimum with a note.
No test touches the network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv5_atlas_view as V  # noqa: E402

GLJS = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


@pytest.fixture(scope="module")
def view():
    if not V.OUT_PATH.exists():
        pytest.skip("view payload not built")
    return json.loads(V.OUT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def atlas():
    if not V.ATLAS_PATH.exists():
        pytest.skip("atlas not built")
    return json.loads(V.ATLAS_PATH.read_text(encoding="utf-8"))


def test_the_payload_names_the_atlas_it_was_built_from(view, atlas):
    assert view["item"] == V.ITEM and view["role"] == "development"
    assert view["served_grade_moves"] is False
    assert view["source"]["sha256"] == V._sha(V.ATLAS_PATH), \
        "the atlas changed since the view was built: run python efv5_atlas_view.py"
    assert view["source"]["generated_at"] == atlas["generated_at"]
    assert view["source"]["tests"] == atlas["tests"]
    assert view["declared"]["min_players"] == atlas["declared"]["min_players"]
    assert view["declared"]["min_pos"] == atlas["declared"]["min_pos"]


def test_every_row_is_the_atlas_row_oriented(view, atlas):
    p = ROOT / atlas["cells_file"]
    if not p.exists():
        pytest.skip("cells file not built")
    cells = json.loads(p.read_text(encoding="utf-8"))
    cix = {c: i for i, c in enumerate(cells["columns"])}
    vix = {c: i for i, c in enumerate(view["columns"])}
    K = view["scale"]
    ids = [m["id"] for m in view["metrics"]]
    seen = 0
    for r in cells["rows"]:
        g = lambda c: r[cix[c]]  # noqa: E731
        key = "|".join((g("side"), g("level"), g("age_band"), g("group"), g("label"), g("frame")))
        rows = {row[vix["m"]]: row for row in view["cells"][key]["rows"]}
        row = rows[ids.index(g("metric"))]
        binary = atlas["labels"][g("label")]["kind"] == "binary"
        if g("raw_full") is None:
            assert row[vix["raw"]] is None
        else:
            want = g("raw_full") if row[vix["dir"]] == 1 else (1 - g("raw_full") if binary else -g("raw_full"))
            assert abs(row[vix["raw"]] / K - want) < 1.5 / K
        if g("incr") is None:
            assert row[vix["incr"]] is None
        else:
            assert abs(row[vix["incr"]] / K - g("incr")) < 1.5 / K
            assert abs(row[vix["incr_lo"]] / K - g("incr_ci95")[0]) < 1.5 / K
        assert row[vix["spent"]] == (1 if g("reserved_overlap") else 0)
        seen += 1
    assert seen == sum(len(c["rows"]) for c in view["cells"].values()) == atlas["tests"]


def test_served_invariants_hold_on_every_row(view):
    vix = {c: i for i, c in enumerate(view["columns"])}
    K = view["scale"]
    minp, minpos = view["declared"]["min_players"], view["declared"]["min_pos"]
    for key, cell in view["cells"].items():
        side, level, band, group, label, frame = key.split("|")
        assert level in view["levels"] and band in view["bands"] and group in view["groups"][side]
        assert label in view["labels"] and frame in view["frames"]
        if frame == "clean":
            assert not cell["spent"], key
        binary = view["labels"][label]["kind"] == "binary"
        assert cell["rows"], key
        for row in cell["rows"]:
            raw, lo, hi = row[vix["raw"]], row[vix["raw_lo"]], row[vix["raw_hi"]]
            if raw is not None:
                assert (K // 2 if binary else 0) <= raw <= K, (key, row)
                assert row[vix["dir"]] in (1, -1)
                assert row[vix["players"]] >= minp and row[vix["pos"]] >= minpos, (key, row)
                if lo is not None and hi is not None:
                    assert lo <= hi
            inc, ilo, ihi, q = (row[vix["incr"]], row[vix["incr_lo"]], row[vix["incr_hi"]],
                                row[vix["q"]])
            if inc is not None:
                assert ilo <= ihi and -K <= inc <= K
                assert q is None or 0 <= q <= K
                assert row[vix["graded"]] >= minp


def test_nothing_is_keyed_or_named_by_an_fv_level(view):
    cell = re.compile(r"\bfv\s*_?\s*(35|40|45|50|55|60|65|70|80)\b", re.I)
    for s in _strings({k: v for k, v in view.items() if k != "cells"}):
        assert chr(0x2014) not in s
        assert not cell.search(s), s
    for key in view["cells"]:
        assert "fv" not in key.lower()


def test_the_chips_are_derived_from_the_selection_artifacts(view):
    select = V._load(V.GROUP_SELECT_PATH)
    head = V._load(V.TRACKING_HEAD_PATH)
    want_admitted = set()
    if select:
        for side_add in select["selected"]["config"]["add"].values():
            for cols in side_add.values():
                for cid in cols:
                    c = select["rule"]["columns"][cid]
                    want_admitted.add((c["side"], c["metric"], c["level"], c["band"], c["group"]))
    if head:
        for side, ws in head["weights"].items():
            for w in ws:
                if w["carries_weight"]:
                    for lv in head["declared"]["levels"]:
                        want_admitted.add((side, f"{V.HEAD_METRIC[w['metric']]}_{side}", lv, "*", "*"))
    got = {(c["side"], c["metric"], c["level"], c["band"], c["group"])
           for c in view["chips"] if c["state"] in ("admitted", "live")}
    assert got == want_admitted
    v5_on = V._flag(V.GROUP_DRIVERS_SRC, "EFV_V5_ON")
    head_on = V._flag(V.TRACKING_HEAD_SRC, "EFV_TRACKING_HEAD_ON")
    if not v5_on and not head_on:
        assert not any(c["state"] == "live" for c in view["chips"])
    ids = {m["id"] for m in view["metrics"]}
    assert all(c["metric"] in ids for c in view["chips"])


def test_chip_rules_follow_the_switch_and_the_ship_rule():
    select = {"rule": {"columns": {
        "a": {"side": "hit", "metric": "woba_hit", "level": "A", "band": "all", "group": "all"},
        "b": {"side": "hit", "metric": "slg_hit", "level": "A", "band": "all", "group": "all"}}},
        "selected": {"config": {"add": {"hit": {"skill": ["a"], "timing": []}}}}}
    head = {"declared": {"levels": ["A"]}, "verdict": {"pit": {"ships": True}},
            "weights": {"pit": [{"metric": "astuff_plus", "carries_weight": True},
                                {"metric": "fb_ivb", "carries_weight": False}]}}
    ships = {"ship_rule": {"ships": True}}
    off = {(r["metric"], r["state"]) for r in V.chip_rules(select, ships, head, False, False)}
    assert off == {("woba_hit", "admitted"), ("slg_hit", "tested"),
                   ("trk_astuff_plus_pit", "admitted"), ("trk_fb_ivb_pit", "tested")}
    on = {(r["metric"], r["state"]) for r in V.chip_rules(select, ships, head, True, True)}
    assert ("woba_hit", "live") in on and ("trk_astuff_plus_pit", "live") in on
    failed = {(r["metric"], r["state"]) for r in
              V.chip_rules(select, {"ship_rule": {"ships": False}}, head, True, True)}
    assert ("woba_hit", "admitted") in failed
    assert V.chip_rules(None, None, None, None, None) == []


def test_the_orientation_flips_the_interval():
    assert V._orient(0.3, 0.25, 0.35, True) == (0.7, 0.65, 0.75, -1)
    assert V._orient(-0.12, -0.2, -0.05, False) == (0.12, 0.05, 0.2, -1)
    assert V._orient(0.6, 0.55, 0.66, True) == (0.6, 0.55, 0.66, 1)


def test_the_view_is_registered_and_reads_the_payload():
    assert '{ id: "metric-atlas", shelf: "evidence", label: "What Predicts the Majors", body: "metric-atlas-body", render: renderMetricAtlas, aliases: [] },' in GLJS
    assert 'fetch("/data/efv5_metric_atlas_view.json"' in GLJS
    assert "A high raw score does not mean a stat beats the scouts." in GLJS
    assert "This group is hidden" in GLJS and "not shown for this group" in GLJS
    start = GLJS.index("// ---- Evidence > What Predicts the Majors")
    block = GLJS[start:GLJS.index("// ---- Library view")]
    assert chr(0x2014) not in block
    # no external attribution: the page does not reproduce the shared chart's figure
    assert "chart_replication" not in block


def test_display_names_cover_every_metric(view):
    for m in view["metrics"]:
        assert m["name"] and "_" not in m["name"], m
