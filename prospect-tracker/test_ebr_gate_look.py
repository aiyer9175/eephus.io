# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/ebr_gate.py, the eBR outcome look (EBR_GATE.md part 5): its refusals, the
floors printed before every estimate, the dry run, the crash protocol and where it
may write. It NEVER runs the real frame: load_inputs is replaced by a tripwire in
every test that reaches the look, and the look's two write targets are temporary
copies.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ebr_gate as G  # noqa: E402

LOOK_DAY = dt.date(2026, 11, 18)
EMPTY_12 = ("## 12. Results\n\n**EMPTY AT REGISTRATION.**\n\n### 12.1 The outcome look (parts 5 and 6)\n\n"
            "EMPTY.\n\n### 12.2 The skill look (parts 9.5 and 9.6)\n\nEMPTY.\n\n"
            "### 12.3 The skill holdout (part 9.5)\n\nEMPTY.\n")
EPOCH_Z = "## 9. Results\n\n### 2026-10-03: step Z, the fWAR label epoch's results\n\ntext\n"
EPOCH_NO_Z = "## 9. Results\n\n### 2026-10-02: the arm set is fixed\n\ntext\n"


def _vintage(drop=None, null=None):
    fields = list(G.VINTAGE_FIELDS) + ["war"]
    seasons = {}
    for s in G.FRAME_SEASONS:
        fl = [f for f in fields if f != drop]
        row = [1.0 for _ in fl]
        if null in fl:
            row[fl.index(null)] = None
        seasons[str(s)] = {"hitting": {"fields": fl, "rows": {"1": row, "2": [1.0 for _ in fl]}}}
    return {"vintage_id": "v", "seasons": seasons}


def _ok_eval():
    return {"identity": {str(s): {"all_pass": True, "I8": {"unchanged": True}} for s in G.FRAME_SEASONS}}


def _ok_sub():
    return {"generated_at": "2026-11-02T00:00:00+00:00",
            "cadence": {"frozen_seasons": list(G.FRAME_SEASONS)}}


def _pre(**kw):
    args = dict(today=LOOK_DAY, waived=False, gate_text=EMPTY_12, epoch_text=EPOCH_Z,
                vintage=_vintage(), preview_eval=_ok_eval(), served_eval=None, substrate=_ok_sub(),
                busy=[], pre_epoch_exists=True)
    args.update(kw)
    return G.preconditions(**args)


# ---------------------------------------------------------------------------
# every refusal
# ---------------------------------------------------------------------------
def test_a_clean_look_day_has_no_refusal():
    assert _pre() == []


def test_refuses_when_part_12_1_is_not_empty():
    filled = EMPTY_12.replace("parts 5 and 6)\n\nEMPTY.", "parts 5 and 6)\n\n**2026-11-18** ran")
    assert any("12.1 is not empty" in w for w in _pre(gate_text=filled))


def test_refuses_when_any_eval_carries_a_look_block():
    ev = _ok_eval()
    ev["look"] = {"status": "started"}
    assert any("preview eval carries a look block" in w for w in _pre(preview_eval=ev))
    assert any("data/ eval carries a look block" in w for w in _pre(served_eval={"look": {}}))


@pytest.mark.parametrize("day", ["2026-10-14", "2026-11-16", "2026-11-17"])
def test_refuses_before_the_date_and_on_excluded_days(day):
    d = dt.date.fromisoformat(day)
    why = _pre(today=d)
    if d < G.LOOK_NOT_BEFORE:
        assert any("is before 2026-11-17" in w for w in why)
    else:
        assert why == []
    assert any("excluded day" in w for w in _pre(today=dt.date(2026, 11, 20)))
    assert any("excluded day" in w for w in _pre(today=dt.date(2026, 12, 1)))


def test_refuses_on_the_skill_looks_day():
    text = EMPTY_12.replace("(parts 9.5 and 9.6)\n\nEMPTY.", "(parts 9.5 and 9.6)\n\n**2026-11-18** skill look")
    assert any("skill look is recorded" in w for w in _pre(gate_text=text))


def test_refuses_without_a_step_z_entry():
    assert any("no step Z entry and step A has started" in w for w in _pre(epoch_text=EPOCH_NO_Z))
    assert any(w.endswith("no step Z entry") for w in _pre(epoch_text=EPOCH_NO_Z, pre_epoch_exists=False))


def test_refuses_on_an_absent_vintage_or_one_lacking_a_field():
    assert any("fwar vintage absent" in w for w in _pre(vintage=None))
    for f in G.VINTAGE_FIELDS:
        assert f"BLOCKER: other fwar vintage lacks {f}" in _pre(vintage=_vintage(drop=f))
        assert f"BLOCKER: other fwar vintage lacks {f}" in _pre(vintage=_vintage(null=f))
    assert G.vintage_missing_fields({"seasons": {}}) == list(G.VINTAGE_FIELDS)


def test_the_blocker_line_prints_verbatim(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "load_inputs", _tripwire)
    monkeypatch.setattr(G, "busy_processes", lambda lines=None: [])
    monkeypatch.setattr(G, "_read_json", lambda p: (_vintage(null="plateAppearances") if Path(p) == G.VINTAGE
                                                    else json.loads(Path(p).read_text(encoding="utf-8"))
                                                    if Path(p).exists() else None))
    ev, doc = _targets(tmp_path)
    rep = G.Report(echo=False)
    assert G.look(rep, today=LOOK_DAY, waived=False, eval_path=ev, doc_path=doc) == 2
    assert "BLOCKER: other fwar vintage lacks plateAppearances" in rep.lines


def test_refuses_a_frame_season_failing_an_identity_gate_or_an_unfrozen_2026():
    ev = _ok_eval()
    ev["identity"]["2021"]["all_pass"] = False
    assert any("failing I1 to I9: [2021]" in w for w in _pre(preview_eval=ev))
    ev = _ok_eval()
    ev["identity"]["2019"]["I8"]["unchanged"] = False
    assert any("[2019]" in w for w in _pre(preview_eval=ev))
    early = {"generated_at": "2026-10-14T00:00:00+00:00",
             "cadence": {"frozen_seasons": [s for s in G.FRAME_SEASONS if s != 2026]}}
    assert any("2026 was built before 2026-11-01" in w for w in _pre(substrate=early))
    assert any("no preview build" in w for w in _pre(substrate=None))


def test_refuses_while_anything_else_runs():
    assert any(w.startswith("busy:") for w in _pre(busy=["12: python run_monthly.py"]))
    me = os.getpid()
    lines = [(me, "python -m pytest x"), (1, "python -m pytest test_a.py"), (2, "python run_monthly.py"),
             (3, "python tools/swar_lab.py"), (4, "python -m http.server 8000"),
             (5, "python -u tools/ebr_gate.py --out-dir x"), (6, "python tools/run_suite.py")]
    busy = G.busy_processes(lines)
    assert [b.split(":")[0] for b in busy] == ["1", "2", "3", "6"]


def test_the_waiver_lifts_the_date_clauses_only():
    early = {"generated_at": "2026-10-14T00:00:00+00:00", "cadence": {"frozen_seasons": [2018]}}
    assert _pre(today=dt.date(2026, 10, 14), waived=True, substrate=early) == []
    assert _pre(today=dt.date(2026, 11, 20), waived=True) == []
    why = _pre(today=dt.date(2026, 10, 14), waived=True, vintage=_vintage(null="plateAppearances"),
               epoch_text=EPOCH_NO_Z, busy=["1: pytest"])
    assert any("lacks plateAppearances" in w for w in why)
    assert any("step Z" in w for w in why) and any(w.startswith("busy") for w in why)


# ---------------------------------------------------------------------------
# floors before d; the dry run
# ---------------------------------------------------------------------------
def test_floors_print_before_every_estimate():
    rep = G.Report(echo=False)
    out = G.run_look(G.synthetic_inputs(), rep, boot=60)
    lines = rep.lines

    def first(prefix):
        return next(i for i, ln in enumerate(lines) if ln.strip().startswith(prefix))
    for name in ("Leg E", "Leg E twin", "E-DP", "E-DP twin", "DP-1", "DP-1 permuted"):
        assert first(f"floors {name}:") < first(f"{name}:"), name
    assert first("BEM+ CONSTANTS") < first("LEG E (5.2)")
    assert first("club changers (primary club") < first("Leg E:")
    for leg in ("leg_e", "leg_e_twin", "e_dp", "e_dp_twin"):
        assert out[leg]["disposition"] in ("SHIP", "RULED OUT", "UNDECIDED", "RESOLVED_LOSS")
        assert set(out[leg]["floors"]) == {"bootstrap_sd", "half_width", "ruled_out_reachable",
                                           "ship_needs_d_above", "resolved_loss_needs_d_below"}
    assert out["leg_e_twin"]["disposition"] == "RESOLVED_LOSS"
    assert out["e_dp_twin"]["disposition"] == "RESOLVED_LOSS"
    assert out["dp1_permuted"]["floor_clear"] is False
    assert set(out["licenses"]) >= {"candidate part 1", "candidate part 2", "copy", "bem_plus", "noise flags"}
    assert chr(0x2014) not in rep.text() and chr(0x2013) not in rep.text()


def test_dispositions_and_floors():
    assert G.disposition(0.10, 0.01) == "SHIP"
    assert G.disposition(-0.10, 0.01) == "RESOLVED_LOSS"
    assert G.disposition(0.0, 0.005) == "RULED OUT"
    assert G.disposition(0.03, 0.02) == "UNDECIDED"
    fl = G.floors(0.0223)
    assert fl["half_width"] == pytest.approx(0.0367, abs=1e-4)
    assert fl["ruled_out_reachable"] is False and fl["ship_needs_d_above"] == pytest.approx(0.0567, abs=1e-4)
    assert (G.BOOT, G.SEED, G.DELTA, G.Z90, G.MIN_PA) == (2000, 20260807, 0.02, 1.645, 300)
    assert G.PAIRS == ((2018, 2019), (2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025), (2025, 2026))
    assert G.FRAME_U == G.PAIRS[:4] and G.LOOK_NOT_BEFORE == dt.date(2026, 11, 17)


def test_the_dry_run_handles_nulls_and_writes_only_its_own_copies(tmp_path):
    before = _snapshot()
    rep = G.Report(echo=False)
    out = G.dry_run(rep, boot=40, out_dir=tmp_path / "dry")
    assert out["frame"]["dropped"]                         # the nulls were met and counted
    assert sorted(p.name for p in (tmp_path / "dry").iterdir()) == ["dry_run_EBR_GATE.md",
                                                                   "dry_run_ebr_eval.json"]
    doc = (tmp_path / "dry" / "dry_run_EBR_GATE.md").read_text(encoding="utf-8")
    assert "EMPTY." not in doc.split("### 12.2")[0] and "verbatim" in doc
    assert json.loads((tmp_path / "dry" / "dry_run_ebr_eval.json").read_text())["look"]["status"] == "dry-run"
    assert _snapshot() == before


def test_the_cli_dry_run_tees_its_output(tmp_path, capsys):
    assert G.main(["--dry-run", "--boot", "30", "--out-dir", str(tmp_path)]) == 0
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    logs = list(tmp_path.glob("ebr_gate_dry_run_*.log"))
    assert len(logs) == 1 and "LEG E (5.2)" in logs[0].read_text(encoding="utf-8")


def test_the_look_needs_an_output_directory(capsys):
    assert G.main([]) == 2


# ---------------------------------------------------------------------------
# where the look writes, and the crash protocol (synthetic inputs, temp targets)
# ---------------------------------------------------------------------------
def _tripwire(*a, **k):
    raise AssertionError("the real frame must never be read in a test")


def _targets(tmp_path):
    ev = tmp_path / "preview" / "ebr_eval.json"
    ev.parent.mkdir(parents=True)
    ev.write_text(json.dumps(_ok_eval()), encoding="utf-8")
    (tmp_path / "preview" / "ebr.json").write_text(json.dumps(_ok_sub()), encoding="utf-8")
    doc = tmp_path / "EBR_GATE.md"
    doc.write_bytes(("# gate\n\n" + EMPTY_12).replace("\n", "\r\n").encode())
    return ev, doc


def test_a_refused_look_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "load_inputs", _tripwire)
    ev, doc = _targets(tmp_path)
    b_ev, b_doc = ev.read_bytes(), doc.read_bytes()
    rep = G.Report(echo=False)
    assert G.look(rep, today=dt.date(2026, 10, 14), waived=False, eval_path=ev, doc_path=doc) == 2
    assert rep.lines[0].startswith("REFUSED")
    assert ev.read_bytes() == b_ev and doc.read_bytes() == b_doc


def test_a_look_writes_part_12_1_and_the_preview_look_block_only(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "preconditions", lambda **k: [])
    monkeypatch.setattr(G, "load_inputs", lambda rep: G.synthetic_inputs())
    monkeypatch.setattr(G, "BOOT", 40)
    ev, doc = _targets(tmp_path)
    before = _snapshot()
    rep = G.Report(echo=False)
    assert G.look(rep, today=dt.date(2026, 10, 14), waived=True, eval_path=ev, doc_path=doc) == 0
    blob = json.loads(ev.read_text(encoding="utf-8"))
    assert blob["look"]["status"] == "complete" and blob["look"]["waived_early_read"] is True
    assert "r_off_B" in blob["look"]["result"]["leg_t"]           # Leg T's r values live in the preview only
    text = doc.read_bytes().decode()
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    sec = text.split("### 12.1 The outcome look (parts 5 and 6)")[1].split("### 12.2")[0]
    assert "2026-10-14" in sec and G.WAIVER_NOTE in sec and "candidate part 1" in sec
    assert text.count("EMPTY.") == 2                              # 12.2 and 12.3 untouched
    assert _snapshot() == before
    # a second run refuses: the look block and part 12.1 are both there now
    monkeypatch.undo()
    monkeypatch.setattr(G, "load_inputs", _tripwire)
    rep2 = G.Report(echo=False)
    assert G.look(rep2, today=LOOK_DAY, waived=False, eval_path=ev, doc_path=doc) == 2
    assert any("12.1 is not empty" in ln for ln in rep2.lines)
    assert any("carries a look block" in ln for ln in rep2.lines)


def test_a_crash_after_scoring_began_leaves_a_look_block_and_no_result(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "preconditions", lambda **k: [])

    def boom(rep):
        raise RuntimeError("synthetic crash")
    monkeypatch.setattr(G, "load_inputs", boom)
    ev, doc = _targets(tmp_path)
    b_doc = doc.read_bytes()
    rep = G.Report(echo=False)
    assert G.look(rep, today=LOOK_DAY, waived=False, eval_path=ev, doc_path=doc) == 3
    assert json.loads(ev.read_text(encoding="utf-8"))["look"]["status"] == "crashed"
    assert doc.read_bytes() == b_doc
    assert any("STOP: no rerun" in ln for ln in rep.lines)


def test_the_look_never_writes_under_data(tmp_path):
    with pytest.raises(G.Refused):
        G.write_look_block({"x": 1}, ROOT / "data" / "ebr_eval.json")
    src = (ROOT / "tools" / "ebr_gate.py").read_text(encoding="utf-8")
    assert "SERVED_EVAL" in src and "write_look_block(started, eval_path)" in src
    assert G.PREVIEW_DIR == ROOT / ".cache" / "ebr" / "preview"


def _snapshot() -> dict:
    """data/ (name, size, sha of the eBR-adjacent files) and the preview eval."""
    out = {"data": sorted((p.name, p.stat().st_size) for p in (ROOT / "data").iterdir() if p.is_file())}
    for p in (ROOT / "data" / "ebr_eval.json", ROOT / "data" / "ebr.json", G.PREVIEW_DIR / "ebr_eval.json",
              G.GATE_DOC):
        out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return out
