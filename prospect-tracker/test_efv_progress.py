# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-00 pins for the eFV progress ledger (efv_progress.py, data/efv_progress.json).

docs/efv-v2/PROGRAM.md s5.4: the ledger copies every number from a named
artifact key and computes none; a second update on unchanged artifacts appends
nothing; old rows are a prefix of new rows; the headline frame is the frame of
head_to_head_verdict.basis; tilted frames carry role "tilted"; `resolvable` is
the artifact's; no key or stratum names a consensus-FV cell
(docs/PROSPECT_ANCHOR_GATE.md); no em-dash in any note.

Every test writes into tmp_path with explicit paths, so none of them can touch
the served ledger or its durable copy.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import efv_progress as P

ROOT = Path(__file__).parent
SB = ROOT / "data" / "source_backtest.json"
SC = ROOT / "data" / "xfv_scoreboard_eval.json"
SERVED = ROOT / "data" / "efv_progress.json"
MV = {"fingerprint": "test-fp|label=ewar_v2@test", "commit": "deadbeef",
      "label": "ewar_v2@test", "resolved_through": 2025}
T0 = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def _real_sb():
    if not SB.exists():
        pytest.skip("data/source_backtest.json absent (gitignored build artifact)")
    doc = json.loads(SB.read_text(encoding="utf-8"))
    if not (doc.get("accuracy") or {}).get("head_to_head_vs_sources"):
        pytest.skip("source_backtest.json predates head_to_head_vs_sources")
    return doc


@pytest.fixture
def arts(tmp_path):
    """A data dir holding the real backtest and scoreboard."""
    _real_sb()
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy2(SB, d / P.SB_NAME)
    if SC.exists():
        shutil.copy2(SC, d / P.SC_NAME)
    return d


def _run(d, now=T0, trigger="nightly"):
    return P.update(d, trigger, out_path=d / "efv_progress.json",
                    ledger_path=d / "ledger.jsonl", now=now, model_version=MV)


def _doc(d):
    return json.loads((d / "efv_progress.json").read_text(encoding="utf-8"))


def _strip(rows):
    return [{k: v for k, v in r.items() if k != "last_verified_at"} for r in rows]


def test_row_numbers_equal_the_artifact_keys(arts):
    sb = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))
    acc = sb["accuracy"]
    hv = acc["head_to_head_verdict"]
    _run(arts)
    doc = _doc(arts)
    head = P.BASIS_TO_FRAME[hv["basis"]]
    vm = [r for r in doc["rows"] if r["frame"] == head]
    assert len(vm) == 1
    r = vm[0]
    blk = acc[hv["basis"]]
    assert r["n"] == hv["n"]
    assert r["raters"]["efv"]["spearman"] == blk["xfv"]["spearman"]
    assert r["raters"]["efv"]["auc"] == blk["xfv"]["auc"]
    for name in ("prospx_consensus", "mlb_pipeline", "fangraphs"):
        assert r["raters"][name]["spearman"] == blk[name]["spearman"]
        assert r["raters"][name]["auc"] == blk[name]["auc"]
    cons = r["deltas"]["vs_prospx_consensus"]["spearman"]
    assert cons["delta"] == hv["delta"]
    assert cons["ci95"] == hv["ci95"]
    assert cons["mde95"] == hv["mde95"]
    vs = acc["head_to_head_vs_sources"]["sources"]
    for src in ("mlb_pipeline", "fangraphs"):
        for metric in ("spearman", "auc"):
            leg = r["deltas"][f"vs_{src}"][metric]
            assert leg["delta"] == vs[src][metric]["delta"]
            assert leg["ci95"] == vs[src][metric]["ci95"]
            assert leg["mde95"] == vs[src][metric]["mde95"]
            # FP3-3: the Holm reading is copied, never recomputed.
            if vs[src][metric].get("holm") is not None:
                assert leg["holm"] == vs[src][metric]["holm"]
                assert leg["holm_verdict"] == vs[src][metric]["verdict"]
    auc = r["deltas"]["vs_prospx_consensus"]["auc"]
    assert auc["delta"] == vs["prospx_consensus"]["auc"]["delta"]
    if vs["prospx_consensus"]["spearman"].get("holm") is not None:
        assert cons["holm"] == vs["prospx_consensus"]["spearman"]["holm"]
        assert cons["holm_verdict"] == vs["prospx_consensus"]["spearman"]["verdict"]
    if hv.get("mde95_status"):
        assert cons["mde95_status"] == hv["mde95_status"] == "carried"
    fl = acc["claim_instruments"]["head_to_head_floors"][P.BY_FRAME_KEY[head]]
    assert r["n_by_side"] == {s: fl["floor_E_cond_by_side"][s]["n"] for s in ("hit", "pit")}
    assert r["resolvable"] == hv["resolvable"]
    assert r["verdict"] == hv["verdict"]
    assert r["window"] == [min(sb["window"]["years"]), max(sb["window"]["years"])]
    assert "source_backtest.json" in {Path(s["path"]).name for s in r["sources"]}
    assert all(s.get("sha256") and s.get("generated_at") for s in r["sources"])
    # Tilted frames copy the by-frame cells.
    for fid, key in (("predebut", "predebut"), ("all_vintages", "all_vintages")):
        cell = acc["head_to_head_by_frame"].get(key)
        if not cell:
            continue
        tr = [x for x in doc["rows"] if x["frame"] == fid][0]
        leg = tr["deltas"]["vs_prospx_consensus"]["spearman"]
        assert leg["delta"] == cell["delta"] and tr["n"] == cell["n"]
        assert tr["resolvable"] == cell["resolvable"]
        assert tr["note"] == cell["basis_note"]


def test_the_verdict_ci_is_the_claim_instrument_interval(arts):
    """One frame, one interval: the verdict's CI95 and the V6 floor's CI95 are
    the same player-clustered bootstrap (same resampler, B and seed)."""
    acc = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))["accuracy"]
    head = P.BASIS_TO_FRAME[acc["head_to_head_verdict"]["basis"]]
    fl = acc["claim_instruments"]["head_to_head_floors"][P.BY_FRAME_KEY[head]]
    assert acc["head_to_head_verdict"]["ci95"] == fl["floor_E_cond_in_run"]["ci95"]


def test_second_update_on_unchanged_artifacts_appends_nothing(arts):
    first = _run(arts)
    assert first["appended"], "the first update wrote no row"
    rows1 = _doc(arts)["rows"]
    second = _run(arts, now=T0 + timedelta(days=1))
    assert second["appended"] == []
    rows2 = _doc(arts)["rows"]
    assert _strip(rows1) == _strip(rows2)
    assert all(r["last_verified_at"] == P._now_iso(T0 + timedelta(days=1)) for r in rows2)


def test_append_only_prefix_property(arts):
    _run(arts)
    rows1 = _doc(arts)["rows"]
    sb = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))
    hv = sb["accuracy"]["head_to_head_verdict"]
    hv["delta"] = round(hv["delta"] + 0.01, 5)
    sb["generated_at"] = "2027-01-01T00:00:00Z"
    (arts / P.SB_NAME).write_text(json.dumps(sb), encoding="utf-8")
    res = _run(arts, now=T0 + timedelta(days=2))
    rows2 = _doc(arts)["rows"]
    assert len(res["appended"]) >= 1
    assert _strip(rows2[:len(rows1)]) == _strip(rows1), "an old row was edited or dropped"
    assert rows2[-1]["frame"] in P.FRAMES


def test_durable_copy_survives_a_checkout_revert(arts):
    """The deploy box runs `git checkout -- .`; a row it appended must come back
    from the untracked ledger on the next update."""
    _run(arts)
    before = (arts / "efv_progress.json").read_text(encoding="utf-8")
    sb = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))
    sb["accuracy"]["head_to_head_verdict"]["delta"] += 0.02
    sb["generated_at"] = "2027-02-01T00:00:00Z"
    (arts / P.SB_NAME).write_text(json.dumps(sb), encoding="utf-8")
    _run(arts, now=T0 + timedelta(days=3))
    grown = _doc(arts)["rows"]
    (arts / "efv_progress.json").write_text(before, encoding="utf-8")   # the revert
    _run(arts, now=T0 + timedelta(days=4))
    back = _doc(arts)["rows"]
    assert [r["run_id"] for r in back] == [r["run_id"] for r in grown]


def test_headline_frame_is_the_verdict_basis_frame(arts):
    _run(arts)
    doc = _doc(arts)
    hv = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))["accuracy"]["head_to_head_verdict"]
    assert doc["headline_frame"] == P.BASIS_TO_FRAME[hv["basis"]] == "vm2"
    head = [r for r in doc["rows"] if r["frame"] == doc["headline_frame"]]
    assert head and all(r["role"] == "headline" for r in head)


def test_tilted_frames_are_tilted_and_never_charted(arts):
    _run(arts)
    doc = _doc(arts)
    for r in doc["rows"]:
        meta = P.FRAMES[r["frame"]]
        assert r["role"] == meta["role"] and r["tilted"] == meta["tilted"]
        if r["frame"] in ("predebut", "all_vintages"):
            assert r["role"] == "tilted" and r["tilted"] is True
    assert not set(doc["chart"]["series_frames"]) & {"predebut", "all_vintages", "disagreement"}
    assert "tilted" in doc["chart"]["excluded_roles"]


def _walk_keys(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_keys(v, out)
    return out


_FV_CELL = re.compile(r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])|tier|fv_cell|fv_bucket",
                      re.I)


def _no_fv_cell(doc):
    bad = [k for k in _walk_keys(doc, []) if _FV_CELL.search(k)]
    assert not bad, f"keys naming an FV cell or tier: {bad}"
    for r in doc.get("rows") or []:
        assert set((r.get("n_by_side") or {})) <= set(P.STRATA)
    assert tuple(doc.get("strata") or ()) == P.STRATA


def _no_emdash(doc):
    txt = json.dumps(doc, ensure_ascii=False)
    assert "—" not in txt and "–" not in txt


def test_no_fv_cell_strata_and_no_emdash(arts):
    _run(arts)
    doc = _doc(arts)
    _no_fv_cell(doc)
    _no_emdash(doc)


def test_the_ledger_layer_computes_no_statistic():
    """No spearman, auc, bootstrap, mean or quantile in the ledger module."""
    src = (ROOT / "efv_progress.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for bad in ("_spearman", "_auc(", "_econd_floor", "_paired_delta_ci", "numpy",
                "statistics", "quantile", "mean(", "sum(", "round("):
        assert bad not in code, f"efv_progress.py computes something: {bad}"


def test_trigger_is_validated(arts):
    with pytest.raises(ValueError):
        P.build_rows({}, None, MV, sources=[], date="2026-09-24",
                     trigger="whenever", now_iso="2026-09-24T00:00:00Z")


def test_served_ledger_contract():
    """The committed data/efv_progress.json obeys the same contract."""
    if not SERVED.exists():
        pytest.skip("data/efv_progress.json not built")
    doc = json.loads(SERVED.read_text(encoding="utf-8"))
    assert doc["schema"] == P.SCHEMA
    assert doc["headline_frame"] == "vm2"
    assert "superseded" in doc["chart"]["excluded_roles"]
    assert "vm" not in doc["chart"]["series_frames"]
    _no_fv_cell(doc)
    _no_emdash(doc)
    ids = [r["run_id"] for r in doc["rows"]]
    assert len(ids) == len(set(ids)), "duplicate run_id"
    for r in doc["rows"]:
        assert r["trigger"] in P.TRIGGERS
        assert r["frame"] in P.FRAMES
        if r["frame"] in ("predebut", "all_vintages"):
            assert r["role"] == "tilted"
        # FP3-1: every stored row of a frame carries that frame's current role.
        assert r["role"] == P.FRAMES[r["frame"]]["role"], (r["run_id"], r["role"])
        if r.get("role_was"):
            assert P.ROLE_CHANGES[r["frame"]][:2] == (r["role_was"], r["role"])
        if r["trigger"] == "backfill":
            for legs in (r.get("deltas") or {}).values():
                for leg in legs.values():
                    assert leg.get("ci95") is None, "a backfilled row carries a CI"
        assert r.get("content_hash") == P.content_hash(r)


# ---------------------------------------------------------------------------
# EV-01 and FP3-1: the timing-pinned frame (vm2) is the headline; vm1 superseded

def test_vm2_headline_row_copies_the_one_verdict_key(arts):
    acc = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))["accuracy"]
    hv = acc["head_to_head_verdict"]
    if hv.get("frame_version") != "vm2":
        pytest.skip("source_backtest.json predates the FP3-1 headline move")
    _run(arts)
    doc = _doc(arts)
    assert doc["headline_frame"] == "vm2"
    vm2 = [r for r in doc["rows"] if r["frame"] == "vm2"]
    assert len(vm2) == 1
    r = vm2[0]
    assert r["role"] == "headline" and r["tilted"] is False
    assert r["frame_version"] == "vm2"
    assert "timing-pinned" in r["note"]
    blk = acc[hv["basis"]]
    assert r["n"] == hv["n"] == blk["xfv"]["n"]
    for name, key in P.RATERS:
        assert r["raters"][name]["spearman"] == blk[key]["spearman"]
        assert r["raters"][name]["auc"] == blk[key]["auc"]
    cons = r["deltas"]["vs_prospx_consensus"]["spearman"]
    assert cons["delta"] == hv["delta"] and cons["ci95"] == hv["ci95"]
    assert cons["mde95"] == hv["mde95"]
    assert cons["key"] == "accuracy.head_to_head_verdict"
    assert r["n_by_side"] == hv["n_by_side"]
    assert r["resolvable"] == hv["resolvable"] and r["verdict"] == hv["verdict"]
    # A fresh artifact writes no vm1 row: vm1 is history, not a live frame.
    assert not [x for x in doc["rows"] if x["frame"] == "vm"]
    assert "vm" not in doc["chart"]["series_frames"]


def test_role_changes_restamp_history_without_touching_its_hash():
    """vm1 rows written as the headline read superseded, vm2 rows written as
    the candidate read headline; the measured content and its hash do not move,
    and a second pass changes nothing."""
    base = {"frame": "vm", "n": 806, "model_id": "efv_v2", "model_version": {},
            "role": "headline", "deltas": {"vs_prospx_consensus": {"spearman": {"delta": 0.007}}}}
    base["content_hash"] = P.content_hash(base)
    cand = dict(base, frame="vm2", role="headline_candidate")
    cand["content_hash"] = P.content_hash(cand)
    other = dict(base, frame="predebut", role="tilted")
    once = P.restamp_roles([base, cand, other])
    assert [r["role"] for r in once] == ["superseded", "headline", "tilted"]
    assert once[0]["role_was"] == "headline" and "FP3-1" in once[0]["role_changed"]
    assert once[1]["role_was"] == "headline_candidate"
    assert "role_was" not in once[2]
    assert [P.content_hash(r) for r in once] == [base["content_hash"], cand["content_hash"],
                                                  P.content_hash(other)]
    assert P.restamp_roles(once) == once
    assert base["role"] == "headline", "restamp_roles edited its input in place"


def test_a_frame_change_is_its_own_trigger_and_never_progress(arts):
    assert "frame_change" in P.TRIGGERS and "frame_change" in P.FRAME_CHANGE_TRIGGERS
    assert "frame_change" not in P.CORRECTION_TRIGGERS
    _run(arts, trigger="frame_change")
    doc = _doc(arts)
    assert doc["frame_change_triggers"] == list(P.FRAME_CHANGE_TRIGGERS)
    assert all(r["trigger"] == "frame_change" for r in doc["rows"])


# ---------------------------------------------------------------------------
# EV-09: development reads of eFV v2 champion H0 (data/efv_v2_dev_eval.json)

DEV = ROOT / "data" / "efv_v2_dev_eval.json"


def _with_dev(arts):
    if not DEV.exists():
        pytest.skip("data/efv_v2_dev_eval.json not built")
    shutil.copy2(DEV, arts / P.DEV_NAME)
    return json.loads(DEV.read_text(encoding="utf-8"))


def test_dev_rows_copy_the_dev_artifact(arts):
    dev = _with_dev(arts)
    _run(arts)
    doc = _doc(arts)
    for fid in P.DEV_FRAMES:
        rows = [r for r in doc["rows"] if r["frame"] == fid
                and r["model_id"] == dev["model_id"]]
        assert len(rows) == 1, fid
        r, f = rows[0], dev["frames"][fid]
        assert r["role"] == "development" and r["tilted"] is False
        assert r["model_id"] == dev["model_id"] != P.MODEL_ID
        assert r["resolvable"] is None and r["verdict"] == f["verdict"]
        assert r["verdict"].startswith("development only")
        assert r["note"] == "development frame, spent, not a claim"
        assert r["n"] == f["n"] and r["window"] == f["window"]
        for name, key in P.DEV_RATERS:
            assert r["raters"][name]["spearman"] == f["raters"][key]["spearman"]
            assert r["raters"][name]["auc"] == f["raters"][key]["auc"]
        for name, comp in P.DEV_DELTAS:
            for metric in ("spearman", "auc"):
                leg, src = r["deltas"][name][metric], f["deltas"][comp][metric]
                assert leg["delta"] == src["delta"] and leg["ci95"] == src["ci95"]
                assert leg["mde95"] == src["mde95"] and leg["resolvable"] is None
        assert r["sources"][0]["path"].endswith(P.DEV_NAME)
        assert r["content_hash"] == P.content_hash(r)
    assert set(P.DEV_FRAMES) <= set(doc["chart"]["series_frames"])


def test_dev_rows_append_once_and_never_displace_v1(arts):
    _with_dev(arts)
    _run(arts)
    assert _run(arts, now=T0 + timedelta(days=1))["appended"] == []
    doc = _doc(arts)
    assert doc["headline_frame"] == "vm2"
    head = [r for r in doc["rows"] if r["frame"] == "vm2"]
    # DS-02: the headline row carries the model the backtest scored (efv_v2 once V2
    # serves), never a development model id
    scored = (((json.loads((arts / P.SB_NAME).read_text(encoding="utf-8")).get("accuracy")
                or {}).get("efv_scored_object") or {}).get("model_id") or P.MODEL_ID)
    assert len(head) == 1 and head[0]["model_id"] == scored
    # a changed development read appends development rows only
    dev = json.loads((arts / P.DEV_NAME).read_text(encoding="utf-8"))
    dev["frames"]["lv_dev"]["raters"]["efv_v2_h0"]["spearman"] += 0.01
    dev["generated_at"] = "2027-03-01T00:00:00Z"
    (arts / P.DEV_NAME).write_text(json.dumps(dev), encoding="utf-8")
    res = _run(arts, now=T0 + timedelta(days=2))
    assert [x.split("|")[1] for x in res["appended"]] == ["lv_dev"]


def test_ds16_rows_copy_the_v2_block_with_its_statistic(arts):
    dev = _with_dev(arts)
    ds = dev.get(P.DS16_SUBKEY)
    if not ds:
        pytest.skip("no DS-16 block in data/efv_v2_dev_eval.json")
    _run(arts)
    doc = _doc(arts)
    for fid in P.DEV_FRAMES:
        rows = [r for r in doc["rows"] if r["frame"] == fid
                and r["model_id"] == ds["model_id"]]
        assert len(rows) == 1, fid
        r, f = rows[0], ds["frames"][fid]
        assert r["role"] == "development" and r["resolvable"] is None
        assert r["model_id"] != dev["model_id"] and r["model_id"] != P.MODEL_ID
        assert r["statistic"] == f["statistic"] and "within" in r["statistic"]
        assert r["note"] == f["note"] and r["verdict"] == f["verdict"]
        for name, key in P.V2_RATERS:
            assert r["raters"][name]["spearman"] == f["raters"][key]["within"]
        for name, comp in P.V2_DELTAS:
            leg, src = r["deltas"][name]["spearman"], f["deltas"][comp]["spearman"]
            assert leg["delta"] == src["delta"] and leg["ci95"] == src["ci95"]
            assert r["secondary"]["deltas"][name]["delta"] == f["deltas"][comp]["pooled"]["delta"]
        assert r["content_hash"] == P.content_hash(r)
    # a rerun appends nothing, and the H0 rows of the same frames keep their place
    assert _run(arts, now=T0 + timedelta(days=1))["appended"] == []
    h0 = [r for r in _doc(arts)["rows"] if r["model_id"] == dev["model_id"]]
    assert {r["frame"] for r in h0} == set(P.DEV_FRAMES)


def test_rows_without_statistic_fields_keep_their_hash():
    row = {"frame": "vm_dev", "n": 1, "model_id": "m", "model_version": {}}
    h = P.content_hash(row)
    assert P.content_hash(dict(row, statistic=None, secondary=None)) == h
    assert P.content_hash(dict(row, statistic="within")) != h


def test_a_non_development_artifact_yields_no_dev_row():
    assert P.build_dev_rows({"role": "look", "frames": {}}, sources=[],
                            date="2026-09-25", trigger="efv_change",
                            now_iso="2026-09-25T00:00:00Z") == []
    with pytest.raises(ValueError):
        P.build_dev_rows({}, sources=[], date="2026-09-25", trigger="whenever",
                         now_iso="2026-09-25T00:00:00Z")


# ---------------------------------------------------------------------------
# SG_5 (efv2026 plan item N7): the frozen 2026 list's frames, registered before
# any read. No row exists yet; these pin where a future row may land.

LV2026 = {
    "lv_2026_surrogate": {"role": "tilted", "tilted": True,
                          "tilt_toward": ("efv on arrival via the timing head; "
                                          "stat readers on production"),
                          "label": "List vintage 2026, one-season surrogate",
                          "note": ("surrogate outcome, tilted by construction, a V2 "
                                   "lead expected by construction, never a claim")},
    "lv_2026_r3": {"role": "tilted", "tilted": True, "tilt_toward": "efv",
                   "label": "List vintage 2026, R3 at RT 2029",
                   "note": "the timing head's own target; tilted, descriptive"},
    "lv_2026_w3": {"role": "secondary", "tilted": False,
                   "label": "List vintage 2026, W3 at RT 2031",
                   "note": ("the frozen frame's registered long-run primary; never "
                            "the headline")},
}
#: The registry before SG_5, by frame id.
_PRE_SG5_FRAMES = {"vm", "vm2", "vm_dev", "lv_dev", "vm_oos_dev", "lv_res", "vm_pros",
                   "predebut", "all_vintages", "disagreement"}


def test_lv2026_frames_are_registered_as_specified():
    assert set(P.FRAMES) == _PRE_SG5_FRAMES | set(LV2026)
    for fid, meta in LV2026.items():
        assert P.FRAMES[fid] == meta, fid
        assert "basis_key" not in P.FRAMES[fid]


def test_lv2026_frames_are_never_charted():
    excluded = ("tilted", "secondary", "superseded")
    for fid in LV2026:
        assert fid not in P.CHART_FRAMES
        assert P.FRAMES[fid]["role"] in excluded
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    m = re.search(r"const _PROG_CHART_FRAMES = \[([^\]]*)\]", js)
    assert m, "_PROG_CHART_FRAMES not found"
    assert not set(re.findall(r'"([^"]+)"', m.group(1))) & set(LV2026)


def test_lv2026_frames_can_never_become_the_headline(arts):
    assert not set(P.BASIS_TO_FRAME.values()) & set(LV2026)
    for table in (P.BY_FRAME_KEY, P.DEFAULT_FRAME_VERSION, P.ROLE_CHANGES):
        assert not set(table) & set(LV2026)
    sb = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))
    for fid in LV2026:
        # A verdict whose basis names the frame still finds no headline frame.
        fake = json.loads(json.dumps(sb))
        fake["accuracy"]["head_to_head_verdict"]["basis"] = fid
        rows = P.build_rows(fake, None, MV, sources=[], date="2026-10-02",
                            trigger="nightly", now_iso="2026-10-02T00:00:00Z")
        assert not [r for r in rows if r["frame"] in LV2026]
        assert P._doc([], fake, "2026-10-02T00:00:00Z",
                      {"headline_frame": "vm2"})["headline_frame"] == "vm2"
    _run(arts)
    doc = _doc(arts)
    assert doc["headline_frame"] == "vm2"
    assert not [r for r in doc["rows"] if r["frame"] in LV2026], "no lv_2026 row exists yet"
    assert not set(doc["chart"]["series_frames"]) & set(LV2026)
    for fid in LV2026:
        assert doc["frames"][fid] == LV2026[fid]


def test_lv2026_registration_changes_no_existing_row():
    """Every stored row keeps its frame's role, its content and its hash: the
    registry gained frames and moved none."""
    if not SERVED.exists():
        pytest.skip("data/efv_progress.json not built")
    doc = json.loads(SERVED.read_text(encoding="utf-8"))
    rows = doc["rows"]
    assert not [r for r in rows if r["frame"] in LV2026]
    assert P.restamp_roles(rows) == rows
    for r in rows:
        assert r["frame"] in _PRE_SG5_FRAMES
        assert r.get("content_hash") == P.content_hash(r)
    for fid, meta in (doc.get("frames") or {}).items():
        if fid in LV2026:
            continue
        for key in ("role", "tilted", "label", "basis_key", "tilt_toward"):
            assert P.FRAMES[fid].get(key) == meta.get(key), (fid, key)


# ---------------------------------------------------------------------------
# EFV3_B8: the screening lab's rows (tools/efv_screen_lab.py; EFV3 LANE_B.md s5).
# Synthetic artifacts in the lab's shapes; nothing here runs the lab.

def _screen_leg(d):
    return {"delta": d, "ci95": [round(d - 0.004, 5), round(d + 0.004, 5)], "mde95": 0.0033,
            "lb95": round(d - 0.0033, 5), "sd": 0.002, "estimator": "E_cond",
            "ci95_estimator": "E_cond, paired, player-clustered", "floor": 0.0061,
            "p_perm": 0.004, "holm_p": 0.028, "reading": "test"}


def _screen_arm(name, side, head, verdict, d, *, exploratory=False, measured=True):
    leg = _screen_leg(d)
    rater = {"spearman": 0.2101 + d, "auc": 0.6402, "n": 900, "within": 0.2101 + d,
             "pooled": 0.2303}
    frame = {"frame_version": "lv1_v2", "window": [2017, 2019], "n": 900,
             "n_by_side": {side: 900}, "statistic": "Spearman within (side, vintage)",
             "raters": {"efv_v2_candidate": rater,
                        "efv_v2_base": dict(rater, spearman=0.2101, within=0.2101),
                        "prospx_consensus": dict(rater, spearman=0.2002, within=0.2002)},
             "deltas": {"candidate_vs_efv_v2_base": {"spearman": leg, "pooled": _screen_leg(d),
                                                     "auc": _screen_leg(d)},
                        "candidate_vs_prospx_consensus": {"spearman": _screen_leg(d + 0.01)}},
             "secondary": {"statistic": "Spearman pooled", "raters": {}, "deltas": {}},
             "verdict": verdict, "note": "screening lab; development frame, spent, not a claim"}
    return {"model_id": f"efv_v2_screen:wave1:{name}:{side}", "measured": measured,
            "verdict": verdict, "within": leg, "frame": frame,
            "screening": {"wave": 1, "head": head, "admitted_folds": 3,
                          "twin_inside_floor": True, "exploratory": exploratory}}


def _screen_doc(exploratory=False):
    return {"generated_at": "2026-10-20T00:00:00Z", "role": "development",
            "exploratory": exploratory, "wave": 1,
            "label": {"provider": "fwar", "resolved_through": 2025, "id": "fwar@test"},
            "code": {"commit": "deadbeef"},
            "arms": [_screen_arm("txt_skill_hit", "hit", "skill", "PASS", 0.0121),
                     _screen_arm("pick_overall_time_pit", "pit", "timing", "NULL", -0.0012),
                     _screen_arm("txt_time_pit", "pit", "timing",
                                 "NOT_ADJUDICATED_EXPLORATORY", 0.0301, exploratory=True),
                     _screen_arm("txt_time_hit", "hit", "timing", None, 0.0, measured=False)]}


def _with_screen(arts, doc=None):
    doc = doc or _screen_doc()
    (arts / P.SCREEN_NAME).write_text(json.dumps(doc), encoding="utf-8")
    return doc


def _screen_rows(doc):
    return [r for r in doc["rows"] if str(r.get("model_id") or "").startswith(P.SCREEN_MODEL_PREFIX)]


def test_screening_rows_copy_the_artifact_keys(arts):
    art = _with_screen(arts)
    _run(arts)
    rows = _screen_rows(_doc(arts))
    by_id = {a["model_id"]: a for a in art["arms"]}
    assert sorted(r["model_id"] for r in rows) == [
        "efv_v2_screen:wave1:pick_overall_time_pit:pit", "efv_v2_screen:wave1:txt_skill_hit:hit"]
    assert any(n == P.SCREEN_NAME and f == ("lv_dev",) and rm is P.SCREEN_RATERS
               and dm is P.SCREEN_DELTAS and sub is None for n, f, rm, dm, sub in P.DEV_ARTIFACTS)
    for r in rows:
        arm = by_id[r["model_id"]]
        f = arm["frame"]
        assert r["frame"] == "lv_dev" and r["role"] == "development" and r["tilted"] is False
        assert r["resolvable"] is None and r["verdict"] == arm["verdict"] == f["verdict"]
        assert r["screening"] == arm["screening"]
        assert set(r["screening"]) == {"wave", "head", "admitted_folds", "twin_inside_floor",
                                       "exploratory"}
        assert r["model_version"]["label"] == art["label"]["id"]
        assert r["n"] == f["n"] and r["window"] == f["window"] and r["statistic"] == f["statistic"]
        assert r["n_by_side"] == f["n_by_side"]
        for name, key in P.SCREEN_RATERS:
            if key not in f["raters"]:
                assert name not in r["raters"]
                continue
            assert r["raters"][name]["spearman"] == f["raters"][key]["spearman"]
            assert r["raters"][name]["auc"] == f["raters"][key]["auc"]
        for name, comp in P.SCREEN_DELTAS:
            for metric, src in (f["deltas"].get(comp) or {}).items():
                if metric not in ("spearman", "auc"):
                    continue
                leg = r["deltas"][name][metric]
                for k in ("delta", "ci95", "mde95") + P.SCREEN_LEG_FIELDS:
                    assert leg[k] == src[k], (r["model_id"], name, metric, k)
                assert leg["resolvable"] is None
        within = r["deltas"]["vs_efv_v2_base"]["spearman"]
        for k in ("delta", "ci95", "lb95", "floor", "holm_p"):
            assert within[k] == arm["within"][k]
        assert r["sources"][0]["path"].endswith(P.SCREEN_NAME)
        assert r["content_hash"] == P.content_hash(r)
    assert set(P._HASH_FIELDS) == {"frame", "frame_version", "window", "n", "n_by_side",
                                   "raters", "deltas", "resolvable", "verdict", "share"}
    assert "screening" in P._OPTIONAL_HASH_FIELDS
    # a rerun on the same artifact appends nothing
    assert _run(arts, now=T0 + timedelta(days=1))["appended"] == []


def test_screen_leg_fields_are_copied_on_screening_rows_only():
    leg = _screen_leg(0.01)
    doc = {"role": "development", "model_id": "efv_v2_h0", "generated_at": "g",
           "frames": {"lv_dev": {"n": 5, "raters": {"efv_v2_h0": {"spearman": 0.3}},
                                 "deltas": {"h0_vs_prospx_consensus": {"spearman": leg}}}}}
    row = P.build_dev_rows(doc, sources=[], date="2026-10-02", trigger="efv_change",
                           now_iso="t")[0]
    assert not set(P.SCREEN_LEG_FIELDS) & set(row["deltas"]["vs_prospx_consensus"]["spearman"])
    scr = dict(doc, screening={"wave": 1, "head": "skill", "admitted_folds": 3,
                               "twin_inside_floor": True, "exploratory": False})
    row = P.build_dev_rows(scr, sources=[], date="2026-10-02", trigger="efv_change",
                           now_iso="t")[0]
    got = row["deltas"]["vs_prospx_consensus"]["spearman"]
    assert {k: got[k] for k in P.SCREEN_LEG_FIELDS} == {k: leg[k] for k in P.SCREEN_LEG_FIELDS}


def test_exploratory_screening_rows_are_never_in_the_chart_series(arts):
    _with_screen(arts)
    _run(arts)
    rows = _screen_rows(_doc(arts))
    assert rows and not [r for r in rows if r["screening"]["exploratory"] is not False]
    assert "efv_v2_screen:wave1:txt_time_pit:pit" not in {r["model_id"] for r in rows}
    # an exploratory artifact lands nothing at all
    assert P.screen_arm_docs(_screen_doc(exploratory=True)) == []
    # the page's series filter draws a screening row only when it is admitted: verdict
    # PASS and exploratory exactly false (assets/glossary.js)
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    series = re.search(r"function _progSeriesRows\(prog\) \{(.*?)\n\}\n", js, re.S).group(1)
    assert "(!_progIsScreen(r) || _progScreenAdmitted(r))" in series
    adm = re.search(r"function _progScreenAdmitted\(r\) \{(.*?)\n\}\n", js, re.S).group(1)
    assert 'r.verdict === "PASS"' in adm and "r.screening.exploratory === false" in adm
    assert "_progIsScreen(r)" in adm


def test_no_screening_row_carries_a_basis_key_or_becomes_the_headline(arts):
    _with_screen(arts)
    _run(arts)
    doc = _doc(arts)
    rows = _screen_rows(doc)
    assert rows
    assert doc["headline_frame"] == "vm2"
    for r in rows:
        assert "basis_key" not in r and r["role"] != "headline"
        assert "basis_key" not in P.FRAMES[r["frame"]]
        assert r["frame"] not in P.BASIS_TO_FRAME.values()
    sb = json.loads((arts / P.SB_NAME).read_text(encoding="utf-8"))
    for basis in ("lv_dev", rows[0]["model_id"], P.SCREEN_NAME):
        fake = json.loads(json.dumps(sb))
        fake["accuracy"]["head_to_head_verdict"]["basis"] = basis
        built = P.build_rows(fake, None, MV, sources=[], date="2026-10-02",
                             trigger="nightly", now_iso="2026-10-02T00:00:00Z")
        assert not [r for r in built if r["role"] == "headline"]
        assert P._doc(rows, fake, "2026-10-02T00:00:00Z",
                      {"headline_frame": "vm2"})["headline_frame"] == "vm2"
    _no_fv_cell(doc)
    _no_emdash(doc)


# ---------------------------------------------------------------------------
# EFV3_D3: the scoreboard matrix pointer (SP/efv3/LANE_D.md s3.7)

MX = ROOT / "data" / "efv_matrix_eval.json"


def _with_matrix(arts, doc=None):
    if doc is None:
        if not MX.exists():
            pytest.skip("data/efv_matrix_eval.json not built")
        shutil.copy2(MX, arts / P.MATRIX_NAME)
        return json.loads(MX.read_text(encoding="utf-8"))
    (arts / P.MATRIX_NAME).write_text(json.dumps(doc), encoding="utf-8")
    return doc


def _file_sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_matrix_field_equals_the_artifact_summary_and_sha(arts):
    mx = _with_matrix(arts)
    _run(arts)
    doc = _doc(arts)
    vm2 = [r for r in doc["rows"] if r["frame"] == "vm2"]
    assert len(vm2) == 1
    m = vm2[0]["matrix"]
    blk = mx["frames"]["vm2"]
    assert tuple(m) == P.MATRIX_FIELDS
    assert Path(m["artifact"]).name == P.MATRIX_NAME
    assert m["sha256"] == _file_sha(arts / P.MATRIX_NAME)
    assert m["generated_at"] == mx["generated_at"]
    assert m["frame_block"] == "vm2"
    assert m["k_family_s"] == blk["summary"]["k_family_s"]
    assert m["summary"] == blk["summary"]["counts"]
    # the pointer is the producer's counts and nothing finer: no cell, no stratum
    assert set(m["summary"]) == set(blk["summary"]["counts"])
    assert "cells" not in m and "families" not in m
    # no tilted or secondary row carries one; every row keeps the two strata only
    for r in doc["rows"]:
        if r["frame"] != "vm2":
            assert "matrix" not in r, r["frame"]
    _no_fv_cell(doc)
    _no_emdash(doc)
    assert "matrix" in P._OPTIONAL_HASH_FIELDS
    assert vm2[0]["content_hash"] == P.content_hash(vm2[0])


def test_a_changed_matrix_appends_one_row_and_an_unchanged_one_none(arts):
    mx = _with_matrix(arts)
    _run(arts)
    rows1 = _doc(arts)["rows"]
    # the same artifact again: nothing appended, only last_verified_at moves
    assert _run(arts, now=T0 + timedelta(days=1))["appended"] == []
    # the producer rewrote the artifact with one cell read differently
    counts = mx["frames"]["vm2"]["summary"]["counts"]
    counts["unresolved"] -= 1
    counts["equivalent"] += 1
    mx["generated_at"] = "2027-04-01T00:00:00Z"
    _with_matrix(arts, mx)
    res = _run(arts, now=T0 + timedelta(days=2))
    assert len(res["appended"]) == 1
    assert res["appended"][0].split("|")[1] == "vm2"
    rows2 = _doc(arts)["rows"]
    assert _strip(rows2[:len(rows1)]) == _strip(rows1), "an old row was edited or dropped"
    new = rows2[-1]
    assert new["frame"] == "vm2" and new["matrix"]["summary"] == counts
    assert new["matrix"]["generated_at"] == "2027-04-01T00:00:00Z"
    assert new["matrix"]["sha256"] == _file_sha(arts / P.MATRIX_NAME)
    # the measured content did not move: only the pointer did
    old = [r for r in rows1 if r["frame"] == "vm2"][-1]
    assert all(old.get(k) == new.get(k) for k in P._HASH_FIELDS)
    assert old["content_hash"] != new["content_hash"]
    # and the new state is now the state: a rerun appends nothing
    assert _run(arts, now=T0 + timedelta(days=3))["appended"] == []


def test_rows_without_matrix_keep_their_hash():
    row = {"frame": "vm2", "n": 1, "model_id": "m", "model_version": {}}
    h = P.content_hash(row)
    assert P.content_hash(dict(row, matrix=None)) == h
    assert P.content_hash(dict(row, matrix={"sha256": "x", "summary": {"ahead": 0}})) != h
    # every committed row predates the pointer and keeps its hash (the served
    # contract test asserts the same over the served file)
    if SERVED.exists():
        for r in json.loads(SERVED.read_text(encoding="utf-8"))["rows"]:
            assert r.get("content_hash") == P.content_hash(r)


def test_absent_matrix_artifact_adds_no_field_and_moves_no_hash(arts):
    _run(arts)
    doc = _doc(arts)
    assert all("matrix" not in r for r in doc["rows"])
    assert all(r["content_hash"] == P.content_hash(r) for r in doc["rows"])


def test_only_the_ds16_development_row_points_at_the_lv_dev_block(arts):
    dev = _with_dev(arts)
    ds = dev.get(P.DS16_SUBKEY)
    if not ds:
        pytest.skip("no DS-16 block in data/efv_v2_dev_eval.json")
    mx = _with_matrix(arts)
    if not ((mx.get("frames") or {}).get("lv_dev") or {}).get("summary", {}).get("counts"):
        pytest.skip("the matrix artifact carries no scored lv_dev block")
    _run(arts)
    doc = _doc(arts)
    for r in doc["rows"]:
        if r["frame"] == "vm2":
            assert r["matrix"]["frame_block"] == "vm2"
        elif r["frame"] == "lv_dev" and r["model_id"] == ds["model_id"]:
            assert r["matrix"]["frame_block"] == "lv_dev"
            assert r["matrix"]["summary"] == mx["frames"]["lv_dev"]["summary"]["counts"]
            assert r["matrix"]["k_family_s"] == mx["frames"]["lv_dev"]["summary"]["k_family_s"]
        else:
            # H0, overlay and P(bust) rows read a different scored object than the
            # matrix's block and carry no pointer, so their hashes stay
            assert "matrix" not in r, (r["frame"], r["model_id"])
        assert r["content_hash"] == P.content_hash(r)
    # vm_dev has no block in the artifact: no pointer, even on the DS-16 row
    assert all("matrix" not in r for r in doc["rows"] if r["frame"] == "vm_dev")


def test_look_row_pointer_copies_the_look_record_strata_block():
    """EFV3_D6 writes the reserved cells under `strata` of data/efv_v2_gate.json;
    a look row copies the same six fields from there and nothing before."""
    assert P.look_matrix_pointer(None, "lv_res") is None
    assert P.look_matrix_pointer({"strata": {}}, "lv_res") is None
    blk = {"frame_id": "lv_res", "cells": {"side": {"hit": {"n": 1}}},
           "summary": {"k_family_s": 12, "counts": {"ahead": 0, "behind": 0, "equivalent": 1,
                                                    "unresolved": 9, "flagged_uncorrected": 0,
                                                    "unpowered": 2, "not_scored": 0,
                                                    "development": 0, "reserved_pending": 0}}}
    gate = {"generated_at": "2026-12-02T00:00:00Z", "strata": {"lv_res": blk}}
    m = P.look_matrix_pointer(gate, "lv_res", sha256="abc")
    assert tuple(m) == P.MATRIX_FIELDS
    assert m["artifact"].endswith(P.GATE_NAME) and m["sha256"] == "abc"
    assert m["generated_at"] == "2026-12-02T00:00:00Z"
    assert m["frame_block"] == "lv_res" and m["k_family_s"] == 12
    assert m["summary"] == blk["summary"]["counts"] and "cells" not in m
    # the matrix artifact's own reserved block (unread, RESERVED_PENDING) is never a pointer
    mx = {"generated_at": "x", "frames": {"lv_res": {"reserved": True, "cells": {},
                                                     "summary": {"reading": "RESERVED_PENDING"}}}}
    assert P.matrix_pointer(mx, "lv_res") is None
    _no_fv_cell({"rows": [{"matrix": m}], "strata": list(P.STRATA)})
