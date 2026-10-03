# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LIBRARY_11: the Model Updates producer (model_updates.py, data/model_updates.json).

Pins the plan's tests (LIBRARY_PLAN.md 4.6, LANE_UPDATES.md 6): every event
reconciles to the artifact key it names (backfilled rows against git show of
their commit); today's eFV row equals the last vm2 ledger row on both legs; the
edge() truth table; `improvement` null unless `same_rows`; append-only prefix;
idempotent rerun; checkout-revert survival; no reserved frame, tilted row or
FV-cell key; copy lint on reader fields; every registry id present; "Other" at
most 10 rows; the note layer and its validator.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import model_registry as R
import model_updates as M

ROOT = Path(__file__).resolve().parent
SERVED = ROOT / "data" / "model_updates.json"
PROGRESS = ROOT / "data" / "efv_progress.json"
TYPED = ROOT / "data" / "model_updates_typed.json"

# test_efv_progress._no_fv_cell's key regex, applied to this file's keys too.
_FV_CELL = re.compile(r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])"
                      r"|tier|fv_cell|fv_bucket", re.I)
_DASHES = ("–", "—")


def _git_ok() -> bool:
    try:
        subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                       check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


GIT = _git_ok()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A backfill into a scratch directory from the real registry, its git
    history and the real progress ledger."""
    if not GIT:
        pytest.skip("git is not available")
    d = tmp_path_factory.mktemp("model_updates")
    res = M.backfill(out_path=d / "mu.json", ledger_path=d / "led.jsonl",
                     typed_path=d / "typed.json")
    assert res["status"] == "ok"
    return d, res["doc"]


@pytest.fixture(scope="module")
def served():
    doc = M.load(SERVED)
    if not doc:
        pytest.skip("data/model_updates.json not built")
    return doc


def _docs(built, served):
    return [("built", built[1]), ("served", served)]


# ---------------------------------------------------------------------------
# the edge rule


def test_edge_truth_table():
    e = M.edge
    # interval
    assert e("Spearman", 0.017, ci=[0.004, 0.03], resolvable=True) == {
        "state": "lead", "text": "Result (Spearman): +0.017 lead"}
    assert e("Spearman", -0.005, ci=[-0.02, 0.01])["text"] == "Result (Spearman): tie (-0.005)"
    assert e("Spearman", -0.03, ci=[-0.05, -0.01]) == {
        "state": "trails", "text": "Result (Spearman): trails by 0.030"}
    # inside the floor: the interval clears zero, the artifact's flag says no
    assert e("Spearman", 0.012, ci=[0.002, 0.02], resolvable=False) == {
        "state": "tie", "text": "Result (Spearman): tie (+0.012, inside the floor)"}
    # the interval covers zero while the flag is True: the all_vintages ledger
    # row of 2026-10-02 (delta 0.0375, mde95 0.0352, ci95 -0.0023 to +0.0743)
    assert e("Spearman", 0.0375, ci=[-0.0023, 0.0743], resolvable=True, mde95=0.0352,
             digits=4) == {"state": "tie", "text": "Result (Spearman): tie (+0.0375)"}
    # one-sided paired t
    assert e("Brier", 0.0055, t=3.371, digits=4)["text"] == "Result (Brier): +0.0055 lead"
    assert e("Brier", 0.0055, t=1.645, digits=4)["state"] == "lead"
    assert e("Brier", 0.001, t=1.2, digits=4)["text"] == "Result (Brier): tie (+0.0010)"
    assert e("Brier", -0.004, t=-2.0, digits=4)["text"] == "Result (Brier): trails by 0.0040"
    # flag only, floor only
    assert e("AUC", 0.0157, resolvable=True)["text"] == "Result (AUC): +0.016 lead"
    assert e("AUC", -0.0157, resolvable=True)["state"] == "trails"
    assert e("AUC", 0.0157, resolvable=False)["state"] == "tie"
    assert e("AUC", 0.02, mde95=0.0078)["state"] == "lead"
    assert e("AUC", -0.02, mde95=0.0078)["state"] == "trails"
    assert e("AUC", 0.005, mde95=0.0078)["state"] == "tie"
    # nothing on record: never lead or trails
    assert e("MAE, years", 0.543) == {
        "state": "unresolved",
        "text": "Result (MAE, years): 0.543 ahead, no interval on record"}
    assert e("Brier", -0.0211, digits=4)["text"] == \
        "Result (Brier): 0.0211 behind, no interval on record"
    # no benchmark, a benchmark without a card, no head-to-head
    assert e(None, benchmark=False) == {"state": "no_benchmark",
                                        "text": "no benchmark registered"}
    assert e(None, wired=False) == {"state": "unwired",
                                    "text": "benchmark named; headline not wired yet"}
    assert e("mean career eWAR", 29.2, contest=False) == {
        "state": "no_contest",
        "text": "Result (mean career eWAR): no head-to-head on record"}


# ---------------------------------------------------------------------------
# reconciliation: every number is the artifact key it names


def _dig(doc, path):
    return R._dig_path(doc, path)


def _check_card_leg(lg, doc):
    k, d = lg["keys"], lg.get("digits")
    assert lg["model"] == M._rnd(_dig(doc, k["model"]), d)
    assert lg["benchmark"] == M._rnd(_dig(doc, k["benchmark"]), d)
    assert lg["delta"] == M._orient(_dig(doc, k["model"]), _dig(doc, k["benchmark"]),
                                    lg["better"], d)
    if "n" in k:
        assert lg["n"] == _dig(doc, k["n"])
    if "ci95" in k:
        lo, hi = _dig(doc, k["ci95"][0]), _dig(doc, k["ci95"][1])
        if k.get("ci95_orientation") == "model_minus_baseline" and lg["better"] == "lower":
            lo, hi = -hi, -lo
        assert lg["ci95"] == [M._rnd(lo, d), M._rnd(hi, d)]
    for f in ("t", "mde95"):
        if f in k:
            assert lg[f] == M._rnd(_dig(doc, k[f]), d)
    if "resolvable" in k:
        assert lg["resolvable"] == M._own_flag(doc, k["resolvable"])


def _reconcile(doc, *, use_git: bool):
    prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
    by_run = {r["run_id"]: r for r in prog["rows"]}
    checked = {"efv": 0, "card_git": 0, "card_tree": 0, "typed": 0}
    reg_cache: dict = {}
    for ev in doc["events"]:
        src = ev.get("source") or {}
        if src.get("path") == M.PROGRESS_REL:
            row = by_run[src["run_id"]]
            for lg in ev["legs"]:
                k = lg["keys"]
                for f in ("model", "benchmark", "n", "delta", "ci95", "mde95"):
                    assert lg[f] == _dig(row, k[f]), (ev["event_id"], f)
            checked["efv"] += 1
        elif ev["kind"] in ("first_scored", "rescored") and ev["layer"] != "typed":
            if src.get("read_from") == "working tree":
                p = ROOT / src["path"]
                if M._sha256(p) != src.get("sha256"):
                    continue          # the artifact moved on since; nothing to compare
                doc_a = json.loads(p.read_text(encoding="utf-8"))
                checked["card_tree"] += 1
            else:
                if not use_git:
                    continue
                raw = M.git_show(src["commit"], src["path"])
                assert raw is not None, ev["event_id"]
                assert M._sha256_bytes(raw) == src["sha256"]
                doc_a = json.loads(raw.decode("utf-8"))
                checked["card_git"] += 1
            for lg in ev["legs"]:
                _check_card_leg(lg, doc_a)
        elif ev["layer"] == "typed":
            if not use_git:
                continue
            key = src["commit"]
            if key not in reg_cache:
                reg_cache[key] = json.loads(M.git_show(key, M.REGISTRY_REL).decode("utf-8"))
            row = next(m for m in reg_cache[key]["models"] if m["model_id"] == ev["model_id"])
            heads = row["card"]["headline"]
            for i, lg in enumerate(ev["legs"]):
                assert lg["model"] == heads[i].get("champion")
                assert lg["benchmark"] == heads[i].get("baseline")
                assert lg["n"] == heads[i].get("n", row["card"].get("n"))
            assert ev["edge"]["state"] == "typed"
            checked["typed"] += 1
    return checked


def test_every_built_event_reconciles_to_its_key(built):
    got = _reconcile(built[1], use_git=True)
    assert got["efv"] >= 20 and got["card_git"] >= 20 and got["typed"] >= 1


def test_every_served_event_reconciles_to_its_key(served):
    got = _reconcile(served, use_git=GIT)
    assert got["efv"] >= 20


def test_today_vm2_row_equals_the_last_ledger_row(built, served):
    prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
    last = [r for r in prog["rows"] if r["frame"] == "vm2"][-1]
    for _name, doc in _docs(built, served):
        efv = next(m for m in doc["models"] if m["model_id"] == "efv_v2")
        legs = {lg["stat"]: lg for lg in efv["today"]}
        assert efv["headline_source"] == "efv_progress"
        for key, stat in (("spearman", "Spearman"), ("auc", "AUC")):
            lg, d = legs[stat], last["deltas"]["vs_prospx_consensus"][key]
            assert lg["delta"] == d["delta"] and lg["ci95"] == d["ci95"]
            assert lg["n"] == last["raters"]["efv"]["n"] == last["n"]
            assert lg["model"] == last["raters"]["efv"][key]
            assert lg["benchmark"] == last["raters"]["prospx_consensus"][key]
            assert lg["source"]["run_id"] == last["run_id"]
        assert legs["Spearman"]["role"] == legs["AUC"]["role"] == "headline"


# ---------------------------------------------------------------------------
# the history's rules


def _all_stat_blocks(doc):
    for ev in doc["events"]:
        if ev.get("statistic"):
            yield ev["event_id"], ev["statistic"]
        for lg in ev.get("legs") or []:
            if "same_rows" in lg:
                yield ev["event_id"], lg


def test_improvement_is_null_unless_same_rows(built, served):
    for _name, doc in _docs(built, served):
        n = 0
        for eid, blk in _all_stat_blocks(doc):
            if not blk.get("same_rows"):
                assert blk.get("improvement") is None, eid
            n += 1
        assert n > 50


def test_the_eFV_model_change_reads_on_identical_rows(built):
    ev = next(e for e in built[1]["events"] if e["model_id"] == "efv_v2"
              and e["kind"] == "model_change" and e["statistic"]["frame"] == "vm2")
    st = ev["statistic"]
    assert (st["before"], st["after"], st["n_before"], st["n"]) == (0.393, 0.4074, 803, 803)
    assert st["same_rows"] and st["improvement"] == 0.0144
    assert ev["edge"]["text"] == "Result (Spearman): tie (-0.0055)"


def test_a_row_drift_is_never_an_improvement(built):
    ev = next(e for e in built[1]["events"] if e["model_id"] == "efv_v2"
              and e["date"] == "2026-09-27" and e["statistic"]["frame"] == "vm2")
    st = ev["statistic"]
    assert (st["n_before"], st["n"], st["same_rows"], st["improvement"]) == (804, 828, False, None)


def _scratch(tmp_path, built):
    d = tmp_path / "w"
    d.mkdir()
    shutil.copy(built[0] / "mu.json", d / "mu.json")
    shutil.copy(built[0] / "led.jsonl", d / "led.jsonl")
    return d


def test_a_second_run_appends_nothing(built, tmp_path):
    d = _scratch(tmp_path, built)
    before = json.loads((d / "mu.json").read_text(encoding="utf-8"))
    led_before = (d / "led.jsonl").read_text(encoding="utf-8")
    res = M.update(out_path=d / "mu.json", ledger_path=d / "led.jsonl",
                   typed_path=built[0] / "typed.json")
    assert res["status"] == "ok" and res["appended"] == []
    after = json.loads((d / "mu.json").read_text(encoding="utf-8"))
    assert [e["event_id"] for e in after["events"]] == [e["event_id"] for e in before["events"]]
    assert (d / "led.jsonl").read_text(encoding="utf-8") == led_before


def _progress_with_new_row(tmp_path):
    prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
    last = dict([r for r in prog["rows"] if r["frame"] == "vm2"][-1])
    last["run_id"] = "2099-01-01T00:00:00Z|vm2|feedbeef"
    last["date"] = "2099-01-01"
    prog["rows"] = prog["rows"] + [last]
    p = tmp_path / "progress.json"
    p.write_text(json.dumps(prog), encoding="utf-8")
    return p


def test_append_only_prefix(built, tmp_path):
    d = _scratch(tmp_path, built)
    before = json.loads((d / "mu.json").read_text(encoding="utf-8"))["events"]
    res = M.update(out_path=d / "mu.json", ledger_path=d / "led.jsonl",
                   progress_path=_progress_with_new_row(tmp_path),
                   typed_path=built[0] / "typed.json")
    assert len(res["appended"]) == 1
    after = json.loads((d / "mu.json").read_text(encoding="utf-8"))["events"]
    strip = lambda e: {k: v for k, v in e.items() if k not in M.PRESENTATION}  # noqa: E731
    assert [strip(e) for e in after[:len(before)]] == [strip(e) for e in before]
    new = after[-1]
    assert new["source"]["run_id"].startswith("2099-01-01")
    assert new["statistic"]["same_rows"] and new["statistic"]["improvement"] == 0.0


def test_the_durable_copy_survives_a_checkout_revert(built, tmp_path):
    d = _scratch(tmp_path, built)
    committed = (d / "mu.json").read_bytes()
    prog = _progress_with_new_row(tmp_path)
    M.update(out_path=d / "mu.json", ledger_path=d / "led.jsonl", progress_path=prog,
             typed_path=built[0] / "typed.json")
    n_after = len(json.loads((d / "mu.json").read_text(encoding="utf-8"))["events"])
    (d / "mu.json").write_bytes(committed)          # what `git checkout -- .` does
    res = M.update(out_path=d / "mu.json", ledger_path=d / "led.jsonl",
                   progress_path=prog, typed_path=built[0] / "typed.json")
    assert res["appended"] == []
    events = json.loads((d / "mu.json").read_text(encoding="utf-8"))["events"]
    assert len(events) == n_after
    assert len({e["event_id"] for e in events}) == len(events)
    assert any(e["source"].get("run_id", "").startswith("2099-01-01") for e in events)


def test_the_nightly_path_never_backfills(tmp_path):
    res = M.update(out_path=tmp_path / "mu.json", ledger_path=tmp_path / "led.jsonl")
    assert res["status"] != "ok" and not (tmp_path / "mu.json").exists()
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert "model_updates.backfill" not in src and "--backfill" not in src


def test_a_second_backfill_is_refused(built, tmp_path):
    d = _scratch(tmp_path, built)
    res = M.backfill(out_path=d / "mu.json", ledger_path=d / "led.jsonl")
    assert res["status"] != "ok"


def test_event_ids_are_unique_and_the_backfill_batch_is_in_date_order(built, served):
    for name, doc in _docs(built, served):
        ids = [e["event_id"] for e in doc["events"]]
        assert len(ids) == len(set(ids)), name
        for e in doc["events"]:
            assert e["content_hash"] == M.content_hash(e), (name, e["event_id"])
            assert e["layer"] in M.LAYERS and e["kind"] in M.KINDS
    days = [e["sort_date"] for e in built[1]["events"]]
    assert days == sorted(days)


def test_the_backfill_receipt(built, served):
    for _name, doc in _docs(built, served):
        b = doc["backfill"]
        assert b["versions_read"] == b["commits"] >= 302
        assert b["rows_emitted"] >= 400 and b["ran_at"] and b["typed_rows"] >= 17


# ---------------------------------------------------------------------------
# never read, never cut, never print


def _keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def _strings(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


def test_no_reserved_frame_no_tilted_row_no_fv_cell_key(built, served):
    for name, doc in _docs(built, served):
        bad = [k for k in _keys(doc, []) if _FV_CELL.search(k)]
        assert not bad, (name, bad[:5])
        txt = json.dumps(doc, ensure_ascii=False)
        # The reserved frames' ids appear nowhere; the tilted and secondary
        # frames' ids are words a model_id may carry (xfv_disagreement_floor),
        # so their test is the run_id form and the copied frame field below.
        for frame in ("lv_res", "vm_pros"):
            assert frame not in txt, (name, frame)
        for frame in ("predebut", "all_vintages", "disagreement", "lv_2026_surrogate",
                      "lv_2026_r3", "lv_2026_w3"):
            assert f"|{frame}|" not in txt, (name, frame)
        vals = set(_strings(doc, []))
        assert not vals & {"reserved", "tilted", "superseded"}, name
        assert "harness_correction" not in txt
        for ev in doc["events"]:
            st = ev.get("statistic") or {}
            if (ev.get("source") or {}).get("path") == M.PROGRESS_REL:
                assert st.get("frame") in M.EFV_FRAMES
                if st.get("frame") == "vm":
                    assert ev["date"] <= M.VM_HEADLINE_THROUGH


def _reader_fields(doc):
    for m in doc["models"]:
        yield m["label"], m["family"], m["edge"]["text"], m.get("benchmark_label")
        for lg in m["today"]:
            yield lg["stat"], lg["edge_text"], lg.get("benchmark_label")
    for ev in doc["events"]:
        yield ev.get("label"), ev.get("family"), ev.get("change"), (ev.get("edge") or {}).get("text")
        yield ((ev.get("benchmark") or {}).get("label"),)
        for lg in ev.get("legs") or []:
            yield lg["stat"], lg["edge_text"], lg.get("benchmark_label")


def test_reader_fields_pass_the_copy_lint(built, served):
    ban = M._ban_re()
    for name, doc in _docs(built, served):
        txt = json.dumps(doc, ensure_ascii=False)
        assert not any(d in txt for d in _DASHES), name
        for tup in _reader_fields(doc):
            for s in tup:
                if s:
                    assert not ban.search(s), (name, s)


def test_every_registry_model_is_present(built, served):
    reg = R.load()
    ids = {m["model_id"] for m in reg["models"]}
    for name, doc in _docs(built, served):
        assert {m["model_id"] for m in doc["models"]} == ids, name
        seen = set()
        for ev in doc["events"]:
            seen |= set(ev.get("registry_ids") or []) | {ev.get("model_id")}
        assert ids <= seen, (name, sorted(ids - seen)[:5])
        assert all(any(e["kind"] == "registered" and e["model_id"] == mid
                       for e in doc["events"]) for mid in ids)


def test_other_holds_at_most_ten_rows(built, served):
    for name, doc in _docs(built, served):
        other = [m["model_id"] for m in doc["models"] if m["family"] == "Other"]
        assert len(other) <= 10, (name, other)
        assert all(m["family"] in M.FAMILIES for m in doc["models"])


def test_route_table_examples():
    reg = {m["model_id"]: m for m in R.load()["models"]}
    want = {"betting_game_prob": "Betting", "arb_award": "Arbitration", "ewar": "eWAR",
            "efv_v2": "PROSPX and eFV", "source_track_record": "Sources and Consensus",
            "hem_plus": "MLB Stats", "fa_market": "Free Agency",
            "team_win_projections": "MLB Projections", "pal_conversion": "Alchemy Lab",
            "draft_slot_curve": "Draft"}
    for mid, fam in want.items():
        assert M.family(reg[mid]) == fam, mid


def test_scored_on_is_the_card_stat_never_the_registry_metric(built):
    reg = {m["model_id"]: m for m in R.load()["models"]}
    for m in built[1]["models"]:
        if m["headline_source"] != "card":
            continue
        heads = reg[m["model_id"]]["card"]["headline"]
        assert [lg["stat"] for lg in m["today"]] == [h.get("stat") or h.get("label")
                                                     for h in heads]


def test_the_producer_computes_no_statistic():
    src = (ROOT / "model_updates.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for bad in ("import numpy", "import pandas", "import statistics", "scipy", "mean(",
                "median(", "quantile", "bootstrap", "spearmanr", "corrcoef"):
        assert bad not in code, bad


def test_run_monthly_hooks():
    import run_monthly
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    daily = src.index('_efv_progress_update(out_dir, "daily")')
    hook = src.index('_model_updates_update(out_dir, "daily")')
    assert 0 < hook - daily < 300
    stamps = src.index("refresh_stamps()", src.index("Model registry freshness pass"))
    monthly = src.index('_model_updates_update(out_dir, "monthly")')
    assert stamps < monthly and "gen_audit_docs.py" in src[stamps:monthly]
    assert "model_updates" in run_monthly.SCHEDULED_EXPORTS
    assert run_monthly._ingest_kind("model_updates") == "export"


def test_the_hook_files_its_heartbeat_and_ingest_row(monkeypatch, tmp_path):
    import job_heartbeat
    import run_monthly
    calls = []
    monkeypatch.setattr(job_heartbeat, "record", lambda name, ok, result="": calls.append(
        (name, ok, result)))
    monkeypatch.setattr(run_monthly, "_INGEST_HEALTH", [])
    monkeypatch.setattr("storage.record_source_check", lambda *a, **k: None, raising=False)
    run_monthly._model_updates_update(tmp_path, "daily")
    assert calls and calls[0][0] == "model_updates" and calls[0][1] is False
    row = run_monthly._INGEST_HEALTH[-1]
    assert row["source"] == "model_updates" and row["ok"] is False


# ---------------------------------------------------------------------------
# the note layer


def _note(**kw):
    n = {"date": "2026-07-23", "model_id": "efv_v1", "text": "the scoreboard was rebuilt",
         "origin": "model upgrades panel", "source": {"commit": "a54e1188"}}
    n.update(kw)
    return n


def _probs(*notes):
    return M.validate_notes({"schema": 1, "notes": list(notes)},
                            [m["model_id"] for m in R.load()["models"]])


def test_note_validator():
    assert _probs(_note()) == []
    assert _probs(_note(date="2026-06")) == []
    assert _probs(_note(date="2026-07-29/30")) == []
    assert _probs(_note(model_id=None, family="Sources and Consensus",
                        text="Glossary reorganized into shelves")) == []
    assert _probs(_note(model_id=None))                      # no family
    assert _probs(_note(model_id="not_a_model"))
    assert _probs(_note(date="July 2026"))
    for w in ("lead", "leads", "leading", "trail", "trails", "trailing", "beat", "beats",
              "win", "wins", "better", "Better", "LEADS"):
        assert _probs(_note(text=f"eFV {w} the consensus")), w
    assert _probs(_note(text="eFV moved — again"))
    assert _probs(_note(text="eFV moved - again"))
    assert _probs(_note(text="the panel was a showcase"))
    assert _probs(_note(text="the gap read 0.031 on that day"))          # figure, no key
    assert _probs(_note(text="the gap read 0.031 on that day",
                        source={"path": "data/x.json", "key": "a.b"})) == []
    # years, dates and version labels are not figures
    assert _probs(_note(text="v38 shipped on 2026-07-23 for the 2027 list, DS-01 and H0")) == []
    assert _probs(_note(origin="somewhere"))


def test_sort_day():
    assert M.sort_day("2026-06") == "2026-06-01"
    assert M.sort_day("2026-07-29/30") == "2026-07-29"
    assert M.sort_day("2026-07-31") == "2026-07-31"


def test_every_typed_note_appears_once(built, tmp_path):
    d = _scratch(tmp_path, built)
    notes = [_note(),
             _note(date="2026-06", model_id=None, family="Sources and Consensus",
                   text="Glossary reorganized", origin="methodology changelog"),
             _note(date="2026-07-29/30", model_id="xfv_hitter",
                   text="the quantile map retired", origin="xfv entry v1 history")]
    typed = tmp_path / "typed.json"
    typed.write_text(json.dumps({"schema": 1, "notes": notes}), encoding="utf-8")
    for _ in range(2):
        res = M.update(out_path=d / "mu.json", ledger_path=d / "led.jsonl", typed_path=typed)
        assert res["note_problems"] == []
    doc = json.loads((d / "mu.json").read_text(encoding="utf-8"))
    got = [e for e in doc["events"] if e["kind"] == "note"]
    assert sorted(e["change"] for e in got) == sorted(n["text"] for n in notes)
    for e in got:
        assert e["layer"] == "note" and e["default_view"]
        assert e["edge"]["text"] == "no score on record for this change"
    by = {e["change"]: e for e in got}
    assert by["Glossary reorganized"]["family"] == "Sources and Consensus"
    assert by["Glossary reorganized"]["date"] == "2026-06"
    assert by["Glossary reorganized"]["sort_date"] == "2026-06-01"
    assert by["the scoreboard was rebuilt"]["label"] == "eFV v1"


def test_the_committed_typed_file_is_valid_and_each_note_is_served_once(served):
    doc = json.loads(TYPED.read_text(encoding="utf-8"))
    ids = [m["model_id"] for m in R.load()["models"]]
    assert M.validate_notes(doc, ids) == []
    texts = [e["change"] for e in served["events"] if e["kind"] == "note"]
    for n in doc["notes"]:
        assert texts.count(n["text"]) == 1, n["text"]
