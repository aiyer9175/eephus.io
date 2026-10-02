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
