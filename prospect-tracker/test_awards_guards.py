"""awards_core.py: THE FRAME GUARDS (AWARDS_2_RULES_CORE; AWARDS_PLAN 2 F10 to F12 and 6
'Invariants and tests' row I7).

The prospect superlatives pair eFV at debut with a season's WAR for one player at a time,
and only on debut cohorts the reserved eFV frames leave open. RESERVED_LV holds LIST
vintages (2020, 2021), whose members debut in 2020 or later, so every 2020 to 2024 debut
cohort waits for the R-LV look record, and every cohort from R_VM_FIRST_DEBUT_YEAR (2025)
waits for its own R-VM look record. The projection superlatives are dark for 2026 and for
any season whose registered looks are not all recorded. No awards module groups a realized
number by FV, eFV or consensus band or reads the realized FV anchor
(docs/PROSPECT_ANCHOR_GATE.md). No test opens a socket.
"""
from __future__ import annotations

import ast
import json
import re
import socket
from pathlib import Path

import pytest

import awards_core as A

ROOT = Path(__file__).resolve().parent
FRAMES = {"lv_first": 2020, "vm_first": 2025}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards guard test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _row(mlbam: int, debut: int, efv: float = 45.0, war: float = 3.0) -> dict:
    return {"mlbam": mlbam, "name": f"P{mlbam}", "club_code": "BOS", "player_key": f"p{mlbam}",
            "debut_season": debut, "efv_at_debut": efv, "war": war, "pa": 600, "ip": 0}


# --- the pool guard ------------------------------------------------------------------------

def test_reserved_frames_read_the_frame_module_pins():
    import efv_vintage_frame as V
    got = A.reserved_frames()
    assert got == {"lv_first": min(V.RESERVED_LV), "vm_first": V.R_VM_FIRST_DEBUT_YEAR} == FRAMES
    assert V.RESERVED_LV == frozenset({2020, 2021})


def test_r_vm_and_r_lv_debut_cohorts_never_enter_the_prospect_pool():
    rows = [_row(1, 2019, 20.0, 5.0), _row(2, 2025, 55.0, 4.0), _row(3, 2026, 60.0, 6.0),
            _row(4, 2022, 50.0, 7.0), _row(5, 2020), _row(6, 2024), _row(7, 2015, 40.0, 1.0)]
    for fn in (A.prospect_above, A.prospect_below):
        block = fn(rows, 2026, war_provider="ewar_v2", frames=FRAMES)
        ids = {r["id"] for r in block["rows"]}
        assert ids == {1, 7}, ids
        assert block["n_pool"] == 2
        assert {r["debut_season"] for r in block["rows"]} == {2019, 2015}
    for y in (2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
        assert A.prospect_pool_open(y, frames=FRAMES) is False, y
    for y in (2011, 2015, 2019):
        assert A.prospect_pool_open(y, frames=FRAMES) is True, y
    # the live pins give the same answer as the fixture frames
    assert A.prospect_pool_open(2019) is True and A.prospect_pool_open(2022) is False
    assert A.prospect_pool_open(2025) is False and A.prospect_pool_open(2026) is False


def test_open_late_cohorts_entries_carry_their_look_record():
    assert isinstance(A.OPEN_LATE_COHORTS, dict)
    for year, entry in A.OPEN_LATE_COHORTS.items():
        assert isinstance(year, int) and year >= FRAMES["lv_first"], year
        assert set(entry) >= {"gate_doc", "results_heading", "record"}, entry
        assert (ROOT / entry["gate_doc"]).exists(), entry["gate_doc"]
        assert A.look_record_exists(entry, ROOT), (
            f"OPEN_LATE_COHORTS names {year} but {entry['gate_doc']} carries no "
            f"{entry['record']} record under {entry['results_heading']!r}")


def test_an_entry_without_its_look_record_fails_and_keeps_the_cohort_closed(monkeypatch, tmp_path):
    entry = {"gate_doc": "docs/efv-v2/EFV_V2_GATE.md", "results_heading": "## 9. Results",
             "record": "R-LV"}
    # at HEAD section 9 holds the empty placeholder only, so the record does not exist
    assert A.look_record_exists(entry, ROOT) is False
    monkeypatch.setitem(A.OPEN_LATE_COHORTS, 2022, entry)
    assert A.prospect_pool_open(2022, frames=FRAMES) is False
    block = A.prospect_above([_row(4, 2022), _row(1, 2019)], 2026, war_provider="ewar_v2", frames=FRAMES)
    assert [r["id"] for r in block["rows"]] == [1]
    with pytest.raises(AssertionError):
        test_open_late_cohorts_entries_carry_their_look_record()
    # the same entry against a document that carries the record opens the cohort
    doc = tmp_path / "docs" / "efv-v2" / "EFV_V2_GATE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# gate\n\n## 8. Rules\n\ntext\n\n## 9. Results\n\n"
                   "| date | frame | verdict |\n|---|---|---|\n| 2026-12-01 | R-LV | read |\n\n"
                   "## 10. Lab\n", encoding="utf-8")
    assert A.look_record_exists(entry, tmp_path) is True
    assert A.prospect_pool_open(2022, root=tmp_path, frames=FRAMES) is True
    # a record under another heading does not count
    other = dict(entry, results_heading="## 10. Lab")
    assert A.look_record_exists(other, tmp_path) is False
    # the placeholder alone never counts, whatever the record name
    doc.write_text("## 9. Results\n\n(Empty. Filled only by the look runner, R-LV included.)\n",
                   encoding="utf-8")
    assert A.look_record_exists(entry, tmp_path) is False


# --- the projection pair ------------------------------------------------------------------

def test_proj_dark_seasons_holds_2026_and_the_pair_is_blocked():
    assert 2026 in A.PROJ_DARK_SEASONS
    rows = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 5.0, "war_proj": 3.0,
             "p10": 1.0, "p90": 5.0, "pa": 600, "ip": 0}]
    for fn in (A.proj_above, A.proj_below):
        block = fn(rows, 2026, war_provider="ewar_v2")
        assert block["rows"] == [] and block["n_pool"] == 0
        assert block["blocked_on"] and "2026" in block["blocked_on"] and "2027" in block["blocked_on"]
    # a season with no PROJ_LOOKS entry is blocked too
    assert 2027 not in A.PROJ_DARK_SEASONS
    msg = A.proj_blocked_on(2027)
    assert msg and "2027" in msg
    assert A.proj_above(rows, 2027, war_provider="ewar_v2")["blocked_on"] == msg
    assert A.proj_above(rows, 2035, war_provider="ewar_v2")["blocked_on"]


def test_proj_pair_lights_only_when_every_registered_look_is_recorded(monkeypatch, tmp_path):
    doc = tmp_path / "docs" / "FORWARD_GATE.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("## 9. Results\n\n| 2027-11-01 | FORWARD-2027 | scored |\n", encoding="utf-8")
    recorded = {"gate_doc": "docs/FORWARD_GATE.md", "results_heading": "## 9. Results",
                "record": "FORWARD-2027"}
    missing = dict(recorded, record="AG_16-2027")
    rows = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 5.0, "war_proj": 3.0,
             "p10": 1.0, "p90": 5.0, "pa": 600, "ip": 0},
            {"mlbam": 2, "name": "B", "club_code": "NYY", "war_realized": 1.0, "war_proj": 4.0,
             "p10": 2.0, "p90": 6.0, "pa": 500, "ip": 0},
            {"mlbam": 3, "name": "C", "club_code": "SEA", "war_realized": 9.0, "war_proj": 1.0,
             "p10": 0.0, "p90": 2.0, "pa": 100, "ip": 0}]
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, (recorded, missing))
    blocked = A.proj_blocked_on(2027, root=tmp_path)
    assert blocked == ("The frozen projection for 2027 is checked against 2027's results after "
                       "its registered looks; this card opens when they are recorded.")
    assert A.proj_looks_pending(2027, root=tmp_path) == ["AG_16-2027"]
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, (recorded,))
    assert A.proj_blocked_on(2027, root=tmp_path) is None
    above = A.proj_above(rows, 2027, war_provider="ewar_v2", root=tmp_path)
    assert above["blocked_on"] is None and [r["id"] for r in above["rows"]] == [1, 2]
    assert above["rows"][0]["from"] == 3.0 and above["rows"][0]["to"] == 5.0
    assert above["rows"][0]["value"] == 2.0 and above["rows"][0]["p90"] == 5.0
    below = A.proj_below(rows, 2027, war_provider="ewar_v2", root=tmp_path)
    assert [r["id"] for r in below["rows"]] == [2, 1] and below["caption"]
    # 2026 stays dark whatever PROJ_LOOKS says
    monkeypatch.setitem(A.PROJ_LOOKS, 2026, (recorded,))
    assert A.proj_blocked_on(2026, root=tmp_path)


# --- the preseason reader (AWARDS_13: PROJ_LOOKS, the frozen file, the Manager column) -----------

_GATES_2027 = {"docs/PROJ_FORWARD_VINTAGE_GATE.md", "docs/AGING_V3_ML_FORWARD_GATE.md",
               "docs/PROJ_COMPONENTS_GATE.md", "docs/TEAM_PROJECTIONS_GATE.md"}


def test_proj_looks_2027_names_the_four_registered_looks_and_their_headings():
    looks = A.PROJ_LOOKS[2027]
    assert {e["gate_doc"] for e in looks} == _GATES_2027
    for e in looks:
        assert set(e) >= {"gate_doc", "results_heading", "record", "record_re", "scope"}, e
        assert set(e["scope"]) <= set(A.PROJ_SCOPES) and e["scope"], e
        doc = ROOT / e["gate_doc"]
        if e.get("pending"):
            # A pending pair keeps the card closed. Once its document lands at HEAD
            # this fails, so the heading and the record pattern are read from it.
            assert not doc.exists(), (
                f"{e['gate_doc']} is at HEAD now: fill its results heading and record_re "
                f"in awards_core.PROJ_LOOKS and drop `pending`")
            assert e["results_heading"] is None and A.look_record_exists(e, ROOT) is False
            continue
        assert doc.exists(), e["gate_doc"]
        lines = [ln.strip() for ln in doc.read_text(encoding="utf-8").splitlines()]
        assert e["results_heading"] in lines, (e["gate_doc"], e["results_heading"])
        re.compile(e["record_re"])
    by_doc = {e["gate_doc"]: e for e in looks}
    # the club column waits for TM_9 as well; the player pair does not read the team look
    assert by_doc["docs/TEAM_PROJECTIONS_GATE.md"]["scope"] == ("clubs",)
    players = {e["gate_doc"] for e in A.proj_looks(2027, "players")}
    clubs = {e["gate_doc"] for e in A.proj_looks(2027, "clubs")}
    assert players == _GATES_2027 - {"docs/TEAM_PROJECTIONS_GATE.md"}
    assert clubs == _GATES_2027
    # 2026 keeps its own decision (AW-Q3) and no look list
    assert 2026 in A.PROJ_DARK_SEASONS and 2026 not in A.PROJ_LOOKS


def test_at_head_2027_is_closed_with_the_pending_sentence_for_both_readers():
    want = ("The frozen projection for 2027 is checked against 2027's results after its "
            "registered looks; this card opens when they are recorded.")
    for scope in A.PROJ_SCOPES:
        assert A.proj_blocked_on(2027, scope=scope) == want
        assert A.proj_looks_pending(2027, scope=scope)
        read = A.preseason_read(2027, scope=scope)
        assert read["blocked_on"] == want and read["vets"] == {} and read["clubs"] == {}
        assert read["file"] is None and read["sha256"] is None
    s26 = A.proj_blocked_on(2026)
    assert s26.startswith("No projection was saved before the 2026 season. ")
    for text in (want, s26, A.proj_blocked_on(2028)):
        assert not A.verdict_hits(text) and A.EM_DASH not in text and A.EN_DASH not in text


def _gate_fixture(root: Path, *, recorded: bool, amended_only: bool = False) -> None:
    """The four gate documents' results sections, with or without the looks' rows."""
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    fwd = ["## 9. The append-only record", "",
           "- 2026-10-09: registered. No frozen file, producer or score exists.",
           "- 2027-03-25: frozen. 2027 preseason file, sha256 abc, score at season end."]
    comp = ["## 9. The append-only record", "", "Empty at registration.", "",
            "| date | gate | verdict | artifact | notes |", "|---|---|---|---|---|",
            "| 2026-11-25 | PJ-C | PASS | data/proj_components_eval.json abc | heads |"]
    team = ["## 8. The append-only record", "", "(no entries)"]
    aging = ["# Aging v3 ML forward gate", "", "## 9. Results", ""]
    if amended_only:
        fwd.append("- 2027-11-10: amendment. The 2027 score moves to 2027-11-12 (AHEAD and BEHIND "
                   "keep their meaning).")
        comp.append("| 2027-11-02 | PJ-W | amendment | none | slip to 2027-11-10 |")
        team.append("- 2027-11-15: amendment. TM_9 moves to 2027-11-20.")
        aging.append("- 2027-10-19: slip. AG_16 moves to 2027-10-21.")
    if recorded:
        fwd.append("- 2027-11-20: the 2027 season-end score. P1 AHEAD, T1 NOT_RESOLVED.")
        comp.append("| 2027-11-21 | PJ-W | UNDERPOWERED | data/proj_components_eval.json def | W1, W2 |")
        team.append("- 2027-11-22: TM_9_TEAM_LOOK_2027 result: TM-D UB95 -0.002, forward_2027 written.")
        aging.append("- 2027-10-20: AG_16 forward look on label season 2027: PASS.")
    (docs / "PROJ_FORWARD_VINTAGE_GATE.md").write_text("\n".join(fwd) + "\n", encoding="utf-8")
    (docs / "PROJ_COMPONENTS_GATE.md").write_text("\n".join(comp) + "\n", encoding="utf-8")
    (docs / "TEAM_PROJECTIONS_GATE.md").write_text("\n".join(team) + "\n", encoding="utf-8")
    (docs / "AGING_V3_ML_FORWARD_GATE.md").write_text("\n".join(aging) + "\n", encoding="utf-8")


def _fixture_looks(season: int) -> tuple:
    """PROJ_LOOKS' 2027 entries with the aging document's heading filled, as the
    commit that drops `pending` would fill it, carried to `season`."""
    out = []
    for e in A.PROJ_LOOKS[2027]:
        e = dict(e)
        if e.get("pending"):
            e.pop("pending")
            e["results_heading"] = "## 9. Results"
            e["record_re"] = (r"^(?!.*\b(?:[Aa]mend\w*|[Ss]lip\w*|VOID)\b)"
                              r"(?=.*\b\d{4}-\d{2}-\d{2}\b)(?=.*\bAG_16\b)")
        if season != 2027 and e.get("record_re"):
            e["record_re"] = e["record_re"].replace("2027", str(season))
        out.append(e)
    return tuple(out)


def test_fixture_gate_documents_open_the_gate_only_with_every_result_row(monkeypatch, tmp_path):
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, _fixture_looks(2027))
    _gate_fixture(tmp_path, recorded=False)
    for scope in A.PROJ_SCOPES:
        assert A.proj_blocked_on(2027, root=tmp_path, scope=scope)
        assert len(A.proj_looks_pending(2027, root=tmp_path, scope=scope)) == (4 if scope == "clubs" else 3)
    # amendment, slip and other-gate rows are not the looks' results
    _gate_fixture(tmp_path, recorded=False, amended_only=True)
    for scope in A.PROJ_SCOPES:
        assert len(A.proj_looks_pending(2027, root=tmp_path, scope=scope)) == (4 if scope == "clubs" else 3)
    _gate_fixture(tmp_path, recorded=True, amended_only=True)
    for scope in A.PROJ_SCOPES:
        assert A.proj_looks_pending(2027, root=tmp_path, scope=scope) == []
        assert A.proj_blocked_on(2027, root=tmp_path, scope=scope) is None
    # one result row missing closes the card again; the team row closes the club column only
    _gate_fixture(tmp_path, recorded=True)
    team = tmp_path / "docs" / "TEAM_PROJECTIONS_GATE.md"
    team.write_text("## 8. The append-only record\n\n(no entries)\n", encoding="utf-8")
    assert A.proj_blocked_on(2027, root=tmp_path, scope="players") is None
    assert A.proj_blocked_on(2027, root=tmp_path, scope="clubs")
    comp = tmp_path / "docs" / "PROJ_COMPONENTS_GATE.md"
    comp.write_text(comp.read_text(encoding="utf-8").replace("| PJ-W | UNDERPOWERED", "| PJ-W | VOID"),
                    encoding="utf-8")
    assert A.proj_looks_pending(2027, root=tmp_path) == ["PJ_11 PJ-W result, label season 2027"]
    # a result row under another heading does not count
    _gate_fixture(tmp_path, recorded=True)
    fwd = tmp_path / "docs" / "PROJ_FORWARD_VINTAGE_GATE.md"
    fwd.write_text(fwd.read_text(encoding="utf-8").replace("## 9. The append-only record",
                                                            "## 8. Clock"), encoding="utf-8")
    assert A.proj_blocked_on(2027, root=tmp_path)


def _frozen_world(tmp_path: Path, season: int, *, label: str | None = "ewar_v2") -> tuple:
    """A freeze log and frozen file for `season` written by M15's own tool."""
    import proj_forward_vintage as pfv
    payload = {"generated_at": f"{season}-03-01", "first_season": season, "horizon": 5,
               "vets": [{"mlbam": 1, "key": "a", "war": [3.0, 2.5], "warP10": [1.0, 1.0],
                         "warP90": [5.0, 5.0]},
                        {"mlbam": 2, "key": "b", "war": [4.0, 3.0], "warP10": [2.0, 2.0],
                         "warP90": [6.0, 6.0]},
                        {"mlbam": 3, "key": "c", "war": [1.0, 1.0], "warP10": [0.0, 0.0],
                         "warP90": [2.0, 2.0]}],
               "team_outlook": [{"team": "BOS", "byYear": [{"wins": 88.0}]},
                                {"team": "NYY", "byYear": [{"wins": 91.0}]}]}
    src = tmp_path / "served.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    vd = tmp_path / "vintage"
    kw = {"label_provider": label} if label else {}
    entry = pfv.freeze(season, src, first_game_pk=1, first_game_date=f"{season}-03-26",
                       source_label="fixture", vintage_dir=vd, frozen_at=f"{season}-03-26", **kw)
    return vd, entry


def test_the_reader_opens_the_file_only_after_the_gate_and_checks_its_hash(monkeypatch, tmp_path):
    import proj_forward_vintage as pfv
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, _fixture_looks(2027))
    vd, entry = _frozen_world(tmp_path, 2027)
    assert entry["label_provider"] == "ewar_v2"
    # pending looks: the freeze log is never opened, so no projected number is loaded
    _gate_fixture(tmp_path, recorded=False)
    real_load = pfv.load_log

    def _refuse(*a, **k):
        raise AssertionError("the frozen file was opened while a look is pending")
    monkeypatch.setattr(pfv, "load_log", _refuse)
    for scope in A.PROJ_SCOPES:
        read = A.preseason_read(2027, scope=scope, root=tmp_path, vintage_dir=vd)
        assert read["blocked_on"] and read["vets"] == {} and read["clubs"] == {}
    monkeypatch.setattr(pfv, "load_log", real_load)
    # every look recorded: the reader reads war[0], warP10[0], warP90[0] and byYear[0].wins
    _gate_fixture(tmp_path, recorded=True)
    players = A.preseason_read(2027, root=tmp_path, vintage_dir=vd)
    assert players["blocked_on"] is None and players["sha256"] == entry["sha256"]
    assert players["label_provider"] == "ewar_v2" and players["clubs"] == {}
    assert players["vets"][1] == {"war": 3.0, "p10": 1.0, "p90": 5.0, "key": "a"}
    assert sorted(players["vets"]) == [1, 2, 3]
    clubs = A.preseason_read(2027, scope="clubs", root=tmp_path, vintage_dir=vd)
    assert clubs["blocked_on"] is None and clubs["vets"] == {}
    assert clubs["clubs"] == {A._club_code("BOS"): 88.0, A._club_code("NYY"): 91.0}
    # the reader writes nothing
    before = {p.name: p.read_bytes() for p in vd.iterdir()}
    A.preseason_read(2027, root=tmp_path, vintage_dir=vd)
    assert {p.name: p.read_bytes() for p in vd.iterdir()} == before
    # a frozen file whose bytes no longer match the log blocks, for both readers
    f = vd / entry["file"]
    f.write_bytes(f.read_bytes() + b" ")
    want = ("The frozen projection file for 2027 does not match the hash in its freeze log, "
            "so this card stays closed.")
    for scope in A.PROJ_SCOPES:
        read = A.preseason_read(2027, scope=scope, root=tmp_path, vintage_dir=vd)
        assert read["blocked_on"] == want and read["vets"] == {} and read["clubs"] == {}
    f.write_bytes(f.read_bytes()[:-1])
    assert A.preseason_read(2027, root=tmp_path, vintage_dir=vd)["blocked_on"] is None
    # a log whose sha256 was edited blocks too
    log = json.loads((vd / pfv.LOG_NAME).read_text(encoding="utf-8"))
    log["entries"][0]["sha256"] = "0" * 64
    (vd / pfv.LOG_NAME).write_text(json.dumps(log), encoding="utf-8")
    assert A.preseason_read(2027, root=tmp_path, vintage_dir=vd)["blocked_on"] == want
    # no freeze at all
    empty = tmp_path / "none"
    empty.mkdir()
    assert A.preseason_read(2027, root=tmp_path, vintage_dir=empty)["blocked_on"] == (
        "No projection for 2027 was frozen before Opening Day, so this card stays closed.")


def test_a_freeze_log_without_the_training_label_keeps_the_player_pair_closed(monkeypatch, tmp_path):
    import proj_forward_vintage as pfv
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, _fixture_looks(2027))
    _gate_fixture(tmp_path, recorded=True)
    vd, entry = _frozen_world(tmp_path, 2027)
    log = json.loads((vd / pfv.LOG_NAME).read_text(encoding="utf-8"))
    del log["entries"][0]["label_provider"]
    (vd / pfv.LOG_NAME).write_text(json.dumps(log), encoding="utf-8")
    read = A.preseason_read(2027, root=tmp_path, vintage_dir=vd)
    assert read["blocked_on"] and "does not name the WAR series" in read["blocked_on"]
    assert read["vets"] == {}
    # the club column reads wins, which carry no WAR series
    assert A.preseason_read(2027, scope="clubs", root=tmp_path, vintage_dir=vd)["blocked_on"] is None


def test_2026_stays_closed_whatever_the_documents_and_the_freeze_log_say(monkeypatch, tmp_path):
    monkeypatch.setitem(A.PROJ_LOOKS, 2026, _fixture_looks(2026))
    _gate_fixture(tmp_path, recorded=True)
    for p in (tmp_path / "docs").iterdir():
        p.write_text(p.read_text(encoding="utf-8").replace("2027", "2026"), encoding="utf-8")
    vd, _ = _frozen_world(tmp_path, 2026)
    assert A.proj_looks_pending(2026, root=tmp_path) == []
    for scope in A.PROJ_SCOPES:
        read = A.preseason_read(2026, scope=scope, root=tmp_path, vintage_dir=vd)
        assert read["blocked_on"].startswith("No projection was saved before the 2026 season. ")
        assert read["vets"] == {} and read["clubs"] == {} and read["file"] is None
    rows = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 5.0, "war_proj": 3.0,
             "p10": 1.0, "p90": 5.0, "pa": 600, "ip": 0}]
    for fn in (A.proj_above, A.proj_below):
        assert fn(rows, 2026, war_provider="ewar_v2", root=tmp_path)["rows"] == []


def _standings():
    return [{"club": "BOS", "league": "AL", "w": 95, "l": 67},
            {"club": "NYY", "league": "AL", "w": 85, "l": 77}]


def _outlook():
    return [{"team": "BOS", "current": {"pythagPct": 0.55, "gamesPlayed": 162}},
            {"team": "NYY", "current": {"pythagPct": 0.53, "gamesPlayed": 162}}]


def test_the_manager_column_lights_only_on_an_open_club_read(monkeypatch, tmp_path):
    monkeypatch.setitem(A.PROJ_LOOKS, 2027, _fixture_looks(2027))
    vd, _ = _frozen_world(tmp_path, 2027)
    earned = {"BOS": 40.0, "NYY": 35.0}
    _gate_fixture(tmp_path, recorded=False)
    pre = A.preseason_read(2027, scope="clubs", root=tmp_path, vintage_dir=vd)
    card = A.manager_ballot(_standings(), _outlook(), earned, "AL", 2027,
                            war_provider="ewar_v2", preseason=pre)
    col = card["preseason_column"]
    assert col["blocked_on"] == pre["blocked_on"] and col["n_rows"] == 0
    for r in card["top"]:
        assert not {"vs_preseason", "vs_preseason_display", "wins_preseason"} & set(r)
    _gate_fixture(tmp_path, recorded=True)
    pre = A.preseason_read(2027, scope="clubs", root=tmp_path, vintage_dir=vd)
    lit = A.manager_ballot(_standings(), _outlook(), earned, "AL", 2027,
                           war_provider="ewar_v2", preseason=pre)
    assert lit["preseason_column"]["blocked_on"] is None and lit["preseason_column"]["n_rows"] == 2
    by = {r["club"]: r for r in lit["top"]}
    bos, nyy = by[A._club_code("BOS")], by[A._club_code("NYY")]
    assert bos["vs_preseason"] == pytest.approx(95 - 88.0) and bos["vs_preseason_display"] == "+7.0"
    assert nyy["vs_preseason"] == pytest.approx(85 - 91.0) and nyy["vs_preseason_display"] == "-6.0"
    # the column never moves the order or the score
    assert [r["club"] for r in lit["top"]] == [r["club"] for r in card["top"]]
    assert [r["score"] for r in lit["top"]] == [r["score"] for r in card["top"]]
    # 2026: closed whatever is on disk; without a preseason argument the card is as before
    assert A.manager_ballot(_standings(), _outlook(), earned, "AL", 2026, war_provider="ewar_v2",
                            preseason={})["preseason_column"]["blocked_on"].startswith(
                                "No projection was saved before the 2026 season.")
    assert "preseason_column" not in A.manager_ballot(_standings(), _outlook(), earned, "AL", 2026,
                                                      war_provider="ewar_v2")


# the payload: a fixture season with pending looks carries no projected value anywhere

#: Keys only the preseason reader's rows carry (next_rise / next_drop print their own
#: projected and realized totals, so those keys are checked on the pair's rows instead).
_PROJ_KEYS = {"war_proj", "wins_preseason", "vs_preseason", "vs_preseason_display"}


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _export_with_frozen(tmp_path, monkeypatch, *, recorded: bool, tamper: bool = False):
    import awards_export as E
    import proj_forward_vintage as pfv
    from test_awards_export import PROV, SEASON, World
    w = World(tmp_path / "world")
    proj = json.loads((w.data / "mlb_projections.json").read_text(encoding="utf-8"))
    sentinels = []
    for i, v in enumerate(proj["vets"]):
        x = round(0.311111111 + i * 1e-9, 9)
        v["war"] = [x] + list(v.get("war") or [])[1:]
        sentinels.append(repr(x))
    for i, t in enumerate(proj["team_outlook"]):
        x = round(80.311111111 + i * 1e-9, 9)
        t["byYear"] = [{"wins": x}] + list(t.get("byYear") or [])[1:]
        sentinels.append(repr(x))
    proj.update(first_season=SEASON, horizon=5, generated_at=f"{SEASON}-03-01")
    src = tmp_path / "frozen_src.json"
    src.write_text(json.dumps(proj), encoding="utf-8")
    vd = tmp_path / "vintage"
    entry = pfv.freeze(SEASON, src, first_game_pk=1, first_game_date=f"{SEASON}-03-26",
                       source_label="fixture", vintage_dir=vd, label_provider=PROV)
    if tamper:
        f = vd / entry["file"]
        f.write_bytes(f.read_bytes() + b"\n")
    gates = tmp_path / "gates"
    _gate_fixture(gates, recorded=recorded)
    for p in (gates / "docs").iterdir():
        p.write_text(p.read_text(encoding="utf-8").replace("2027", str(SEASON)), encoding="utf-8")
    monkeypatch.setattr(A, "PROJ_DARK_SEASONS", frozenset())
    monkeypatch.setitem(A.PROJ_LOOKS, SEASON, _fixture_looks(SEASON))
    monkeypatch.setattr(E, "GATE_ROOT", gates)
    monkeypatch.setattr(E, "PROJ_VINTAGE_DIR", vd)
    old = E._display_provider
    E._display_provider = lambda: PROV
    try:
        res = w.export()
    finally:
        E._display_provider = old
        E.reset_frames()
    assert res["ok"], res
    files = {p.name: p.read_bytes() for p in w.preview.iterdir() if p.is_file()}
    return w.read("awards.json"), files, sentinels


def _proj_cards(awards):
    return [s for s in awards["superlatives"] if s["id"] in ("proj_above", "proj_below")]


def test_pending_looks_leave_no_projected_value_anywhere_in_the_payload(monkeypatch, tmp_path):
    awards, files, sentinels = _export_with_frozen(tmp_path, monkeypatch, recorded=False)
    want = (f"The frozen projection for {awards['season']} is checked against "
            f"{awards['season']}'s results after its registered looks; this card opens when "
            f"they are recorded.")
    for s in _proj_cards(awards):
        assert s["rows"] == [] and s["n_pool"] == 0 and s["blocked_on"] == want
    for lg, card in awards["awards"]["MOY"].items():
        assert card["preseason_column"]["blocked_on"] == want
        assert card["preseason_column"]["n_rows"] == 0
    assert awards["stamp"]["preseason_file"]["blocked_on"] == want
    assert awards["stamp"]["preseason_file"]["sha256"] is None
    for name, raw in files.items():
        doc = json.loads(raw.decode("utf-8"))
        for k, v in _walk(doc):
            assert not (k in _PROJ_KEYS and v is not None), (name, k, v)
        text = raw.decode("utf-8")
        for x in sentinels:
            assert x not in text, (name, x)


def test_recorded_looks_light_the_pair_and_the_column_from_the_frozen_file(monkeypatch, tmp_path):
    awards, files, sentinels = _export_with_frozen(tmp_path, monkeypatch, recorded=True)
    lit = _proj_cards(awards)
    assert len(lit) == 2
    for s in lit:
        assert s["blocked_on"] is None and s["rows"], s
        assert s["war_provider"] == "ewar_v2" and s["preseason_file"]["label_provider"] == "ewar_v2"
        for r in s["rows"]:
            assert repr(r["from"]) in sentinels
            assert r["value"] == pytest.approx(r["to"] - r["from"])
    for lg, card in awards["awards"]["MOY"].items():
        assert card["preseason_column"]["blocked_on"] is None
        assert card["preseason_column"]["n_rows"] > 0
        assert any(repr(r.get("wins_preseason")) in sentinels for r in card["top"])
    assert awards["stamp"]["preseason_file"]["sha256"]


def test_a_tampered_frozen_file_closes_the_pair_in_the_payload(monkeypatch, tmp_path):
    awards, files, sentinels = _export_with_frozen(tmp_path, monkeypatch, recorded=True, tamper=True)
    for s in _proj_cards(awards):
        assert s["rows"] == [] and "does not match the hash" in s["blocked_on"]
    for card in awards["awards"]["MOY"].values():
        assert "does not match the hash" in card["preseason_column"]["blocked_on"]
    for raw in files.values():
        text = raw.decode("utf-8")
        assert not any(x in text for x in sentinels)


# --- the anchor gate: no grouping by band, no read of the realized anchor ------------------------

_BAND_ID = re.compile(r"(^|_)(x?fv|efv|consensus)_?(band|bucket|cell|tier|bin|group|strat\w*)",
                      re.IGNORECASE)
_ANCHOR = re.compile(r"fv_to_6yr_avg_war|fv[_\s-]*to[_\s-]*war|FV-to-WAR", re.IGNORECASE)
_GROUPERS = {"groupby", "pivot_table", "cut", "qcut", "crosstab"}


def _awards_modules() -> list[Path]:
    return sorted(p for p in ROOT.glob("awards_*.py"))


def _identifiers(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 80:
            yield node.value, node.lineno


def test_no_awards_module_groups_by_an_fv_band_or_reads_the_anchor():
    mods = _awards_modules()
    assert {p.name for p in mods} >= {"awards_core.py", "awards_rookies.py"}
    for p in mods:
        src = p.read_text(encoding="utf-8")
        assert not _ANCHOR.search(src), f"{p.name} names the realized FV anchor"
        tree = ast.parse(src)
        for ident, line in _identifiers(tree):
            assert not _BAND_ID.search(ident), f"{p.name}:{line} groups by an FV band: {ident!r}"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in _GROUPERS:
                text = ast.unparse(node).lower()
                assert not re.search(r"fv|efv|consensus", text), f"{p.name}:{node.lineno}: {text}"
        # the module imports nothing that serves the realized anchor
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                for n in names:
                    assert not re.search(r"anchor|fv_war|fv_to", n, re.IGNORECASE), f"{p.name}: {n}"


def test_prospect_rows_are_per_player_and_never_aggregated():
    rows = [_row(i, 2015 + (i % 5), efv=20.0 + i, war=float(i) / 2) for i in range(1, 13)]
    block = A.prospect_above(rows, 2026, war_provider="ewar_v2", frames=FRAMES)
    assert all(isinstance(r["id"], int) for r in block["rows"])
    keys = set()
    for r in block["rows"]:
        keys |= set(r)
    assert not any(_BAND_ID.search(k) for k in keys)
    assert not any(k in ("mean", "median", "count", "rate", "n_by_band") for k in keys)


# --- the provider ----------------------------------------------------------------------------

def test_awards_core_never_reads_the_training_default():
    src = (ROOT / "awards_core.py").read_text(encoding="utf-8")
    assert "DEFAULT_PROVIDER" not in src
    assert "served_war_basis" in src
    with pytest.raises(ValueError):
        A.league_split({"bat": [], "pit": []}, season=2026, war_provider=None)
    with pytest.raises(ValueError):
        A.war_unit_label("")
    assert A.war_unit_label("ewar_v2") == "eWAR v2" and A.war_unit_label("ewar_v3") == "eWAR v3"


def test_flag_is_off_and_nothing_served_names_awards():
    assert A.AWARDS_LIVE is False
    assert "awards" not in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").split()
    for name in ("glossary.json", "model_registry.json"):
        text = (ROOT / "data" / name).read_text(encoding="utf-8")
        assert '"awards_selection"' not in text and '"eephus_selection"' not in text, name
    assert not (ROOT / "awards" / "index.html").exists()
    assert not (ROOT / "data" / "awards.json").exists()
