"""The forward vintage of the MLB projections and the first-season flip guard.

docs/PROJ_FORWARD_VINTAGE_GATE.md (owner answers M15-2 and M15-3, 2026-09-25).
The preseason projections are frozen once, before the season's first game, and
proj_export refuses to roll FIRST_SEASON past a season whose forecast is not on
record. A freeze is only evidence if nobody can edit it afterwards, so the
folder's log is re-verified here on every run, and the freeze commit adds the
season's hash below as a literal (as test_provisional_freeze_pin.py does).
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

import proj_export as pe
import proj_forward_vintage as pfv

ROOT = Path(__file__).resolve().parent

#: season -> sha256 of the frozen file, added by hand in the freeze commit.
#: Empty until the 2027 freeze (first game of 2027, before first pitch).
PINNED_SHA256: dict[int, str] = {}


def _payload(first_season=2027, generated_at="2027-03-20"):
    return {
        "generated_at": generated_at, "first_season": first_season, "horizon": 5,
        "vets": [
            {"key": "a_b", "mlbam": 1, "war": [3.1, 2.9], "warP10": [0.4, 0.2],
             "warP90": [5.8, 5.5]},
            {"key": "c_d", "mlbam": 2, "war": [0.5], "warP10": [0.0], "warP90": [1.9]},
        ],
        "team_outlook": [
            {"team": "LAD", "byYear": [{"season": first_season, "wins": 96.4}]},
            {"team": "COL", "byYear": [{"season": first_season, "wins": 64.1}]},
        ],
    }


def _write(tmp: Path, payload: dict, name="src.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return p


def _freeze(tmp: Path, payload=None, **kw):
    src = _write(tmp, payload or _payload())
    vd = tmp / "vintage"
    entry = pfv.freeze(kw.pop("season", 2027), src, first_game_pk=kw.pop("pk", 778899),
                       first_game_date=kw.pop("first_game_date", "2027-03-25"),
                       source_label="test", vintage_dir=vd, frozen_at="2027-03-25", **kw)
    return vd, entry


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------
def test_the_guard_is_a_no_op_at_the_first_frozen_season(tmp_path):
    assert pfv.FIRST_FROZEN_SEASON == 2027
    pe.assert_first_season_flip_allowed(2027, tmp_path / "empty")


def test_the_guard_refuses_a_flip_past_an_unfrozen_season(tmp_path):
    with pytest.raises(RuntimeError, match="2027"):
        pe.assert_first_season_flip_allowed(2028, tmp_path / "empty")


def test_the_guard_accepts_a_flip_once_the_season_is_frozen(tmp_path):
    vd, _ = _freeze(tmp_path)
    pe.assert_first_season_flip_allowed(2028, vd)
    # every season up to the new first season must be on record, not only the last
    with pytest.raises(RuntimeError, match="2028"):
        pe.assert_first_season_flip_allowed(2029, vd)


def test_the_guard_refuses_when_the_frozen_bytes_change(tmp_path):
    vd, entry = _freeze(tmp_path)
    f = vd / entry["file"]
    f.write_bytes(f.read_bytes().replace(b"96.4", b"99.9"))
    with pytest.raises(RuntimeError, match="sha256"):
        pe.assert_first_season_flip_allowed(2028, vd)


def test_the_guard_refuses_when_the_logged_extract_changes(tmp_path):
    vd, _ = _freeze(tmp_path)
    log_p = vd / pfv.LOG_NAME
    log = json.loads(log_p.read_text(encoding="utf-8"))
    log["entries"][0]["extract"]["vets"][0]["war0"] = 9.9
    log_p.write_text(json.dumps(log), encoding="utf-8")
    with pytest.raises(RuntimeError, match="extract"):
        pe.assert_first_season_flip_allowed(2028, vd)


def test_a_no_season_entry_counts_only_with_its_amendment(tmp_path):
    vd = tmp_path / "vintage"
    vd.mkdir()
    entry = {"season": 2027, "status": "no_season"}
    (vd / pfv.LOG_NAME).write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="amendment"):
        pe.assert_first_season_flip_allowed(2028, vd)
    entry["amendment"] = "docs/PROJ_FORWARD_VINTAGE_GATE.md section 9, 2027-10-01"
    (vd / pfv.LOG_NAME).write_text(json.dumps({"entries": [entry]}), encoding="utf-8")
    pe.assert_first_season_flip_allowed(2028, vd)


def test_build_payload_runs_the_guard_first():
    import inspect
    src = inspect.getsource(pe.build_payload)
    assert src.index("assert_first_season_flip_allowed()") < src.index("_build_payload_body()")


def test_the_served_first_season_is_allowed_on_this_tree():
    pe.assert_first_season_flip_allowed()


def test_the_flip_is_dated():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", pe.FIRST_SEASON_SET_ON)
    assert date.fromisoformat(pe.FIRST_SEASON_SET_ON) <= date.today()


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------
def test_the_freeze_is_byte_identical_and_logs_its_extract(tmp_path):
    vd, entry = _freeze(tmp_path)
    src = tmp_path / "src.json"
    assert (vd / entry["file"]).read_bytes() == src.read_bytes()
    assert entry["file"] == "mlb_projections_2027_preseason.json"
    assert entry["sha256"] == pfv.sha256_bytes(src.read_bytes())
    assert entry["extract"] == {
        "vets": [{"mlbam": 1, "key": "a_b", "war0": 3.1, "warP10_0": 0.4, "warP90_0": 5.8},
                 {"mlbam": 2, "key": "c_d", "war0": 0.5, "warP10_0": 0.0, "warP90_0": 1.9}],
        "team_outlook": [{"team": "LAD", "wins0": 96.4}, {"team": "COL", "wins0": 64.1}]}
    assert entry["first_game"] == {"gamePk": 778899, "gameDate": "2027-03-25"}
    assert pfv.check(vd) == []


def test_the_freeze_records_the_training_label(tmp_path, monkeypatch):
    # gate section 5 "The labels": the label the frozen file was trained on is in the log
    meta = json.loads(pfv.BUNDLE_META.read_text(encoding="utf-8"))
    vd, entry = _freeze(tmp_path)
    assert entry["label_provider"] == meta["war_provider"]
    assert json.loads((vd / pfv.LOG_NAME).read_text(encoding="utf-8"))["entries"][0][
        "label_provider"] == meta["war_provider"]
    (tmp_path / "given").mkdir()
    vd2, entry2 = _freeze(tmp_path / "given", label_provider="ewar_v2")
    assert entry2["label_provider"] == "ewar_v2" and pfv.check(vd2) == []
    # no label anywhere: the freeze refuses and writes nothing
    monkeypatch.setattr(pfv, "BUNDLE_META", tmp_path / "missing_meta.json")
    (tmp_path / "none").mkdir()
    with pytest.raises(ValueError, match="no training label"):
        _freeze(tmp_path / "none")
    assert not (tmp_path / "none" / "vintage").exists()


def test_the_freeze_is_write_once(tmp_path):
    vd, _ = _freeze(tmp_path)
    src = _write(tmp_path, _payload(generated_at="2027-03-24"), "later.json")
    with pytest.raises(ValueError, match="write-once"):
        pfv.freeze(2027, src, first_game_pk=1, first_game_date="2027-03-25",
                   source_label="test", vintage_dir=vd)


@pytest.mark.parametrize("payload, why", [
    (_payload(first_season=2026), "first_season"),
    (_payload(generated_at="2027-03-26"), "after the first game"),
    ({**_payload(), "vets": [{"key": "x", "mlbam": 3, "war": [1.0], "warP10": []}]}, "warP10"),
    ({**_payload(), "team_outlook": [{"team": "NYM", "byYear": []}]}, "byYear"),
])
def test_the_freeze_refuses_a_file_that_is_not_the_preseason_forecast(tmp_path, payload, why):
    src = _write(tmp_path, payload)
    with pytest.raises(ValueError, match=why):
        pfv.freeze(2027, src, first_game_pk=1, first_game_date="2027-03-25",
                   source_label="test", vintage_dir=tmp_path / "vintage")
    assert not (tmp_path / "vintage" / pfv.frozen_name(2027)).exists()


def test_the_cli_check_writes_nothing(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "freeze_tool", ROOT / "tools" / "freeze_proj_forward_vintage.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    vd, _ = _freeze(tmp_path)
    before = {p.name: p.read_bytes() for p in vd.iterdir()}
    assert tool.main(["--check", "--vintage-dir", str(vd)]) == 0
    assert {p.name: p.read_bytes() for p in vd.iterdir()} == before


# ---------------------------------------------------------------------------
# the real folder
# ---------------------------------------------------------------------------
def test_every_logged_freeze_still_verifies():
    assert pfv.check() == []


def test_every_frozen_season_is_pinned_by_a_literal():
    entries = [e for e in pfv.load_log()["entries"] if e.get("status") == "frozen"]
    for e in entries:
        assert PINNED_SHA256.get(e["season"]) == e["sha256"], (
            f"pin the {e['season']} freeze: PINNED_SHA256[{e['season']}] = '{e['sha256']}'")
    assert set(PINNED_SHA256) <= {e["season"] for e in entries}


def test_the_folder_is_evidence_not_a_served_payload():
    rel = pfv.VINTAGE_DIR.relative_to(ROOT).as_posix()
    assert rel == "data/proj_forward_vintage"      # below data/ depth one: never shipped
    publish = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert "proj_forward_vintage" not in publish
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "data/proj_forward_vintage/** -text" in attrs


def test_the_gate_is_registered():
    doc = (ROOT / "docs" / "PROJ_FORWARD_VINTAGE_GATE.md").read_text(encoding="utf-8")
    for needle in ("WRITE-ONCE", "FREEZE_LOG.json", "assert_first_season_flip_allowed",
                   "NOT_RESOLVED", "no_season"):
        assert needle in doc, needle

