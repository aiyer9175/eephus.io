# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_2 pins (docs/efv-v2/SURROGATE_2026_GATE.md s2.3 and precondition Q4): the surrogate
guard beside the R-LV guard.

1. efv_vintage_frame.py is not edited by the surrogate lane (git blob pin) and its two
   guard functions keep their signatures.
2. A DRAFT surrogate gate never opens the surrogate guard. Fixture ONE (the surrogate
   gate REGISTERED beside EFV_V2_GATE.md as a DRAFT) opens V 2019 for the transfer
   read and never opens guard_score_request(2020) or (2021). Fixture TWO (both
   REGISTERED) shows gate_sha_committed accepting that sha while the surrogate guard
   still refuses V 2020 and 2021 for every purpose.
3. One test per refusal in the schedule of s2.3; records are claimed only by
   data/efv_v2_gate.json; a V 2026 read refuses without the ETA look record.
4. withhold_reserved_vm refuses (never drops) without the owning record and returns
   every row, event-only, with it.
5. blocked_day refuses on the registered look days, the reserved-read day and while
   another gate's look marker is present.
6. The surrogate modules never call guard_score_request, import no outcome module and
   read no debut or major league column on the identity path (the DS-03 pattern).

Every repository here is a scratch fixture or the real HEAD read through git; every row
is synthetic. Nothing computes an outcome, a label or a score.
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import subprocess
from pathlib import Path

import pytest

import efv_labels as L
import efv_surrogate_guard as G
import efv_vintage_frame as F

ROOT = Path(__file__).parent

#: git blob of efv_vintage_frame.py at the lane's base b5b0ae8a (and at the integration
#: head 6c080ecd); the plan's c9d5a29d is the blob at 64bf1bb3 and 26b446d9, before
#: 6fd30aee and fc5b9cc0 changed the file.
VINTAGE_FRAME_BLOB = "09430d3b211c67a480b51aff0dbfb27d8f4ca669"
SURR = G.SURROGATE_GATE_DOC
EFV = F.GATE_DOC


# ---------------------------------------------------------------------------
# 1. the R-LV guard is untouched
# ---------------------------------------------------------------------------

def test_vintage_frame_blob_is_pinned():
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD:./efv_vintage_frame.py"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("not a git checkout")
    assert r.stdout.strip() == VINTAGE_FRAME_BLOB


def test_the_r_lv_guard_keeps_its_signatures_and_doc():
    assert str(inspect.signature(F.gate_sha_committed)) == "(gate_sha: 'str | None') -> 'bool'"
    assert str(inspect.signature(F.guard_score_request)) == \
        "(vintage: 'int', *, gate_sha: 'str | None' = None, purpose: 'str' = 'score') -> 'None'"
    assert F.GATE_DOC == "docs/efv-v2/EFV_V2_GATE.md"
    assert G.SURROGATE_GATE_DOC == "docs/efv-v2/SURROGATE_2026_GATE.md" != F.GATE_DOC
    assert G.RESERVED_LV is F.RESERVED_LV and G.ReservedFrameError is F.ReservedFrameError


def test_reserved_vm_pins_still_empty():
    assert F.reserved_vm_pins() == []


def test_windows_and_cohorts_match_the_label_module():
    assert G.DEBUT_WINDOW_SEASONS["transfer"] == L.W_DEBUT_WINDOW
    assert G.DEBUT_WINDOW_SEASONS["lv2026_long_run"] == L.W_DEBUT_WINDOW
    assert G.DEBUT_WINDOW_SEASONS["lv2026_surrogate"] == 0
    assert min(G.COHORT_RELEASE) == F.R_VM_FIRST_DEBUT_YEAR
    assert set(G.DEBUT_WINDOW_SEASONS) == set(G.PURPOSES)


# ---------------------------------------------------------------------------
# fixture repository
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _doc(status: str, oq2: str | None = None) -> str:
    head = f"# gate\n\nRegistration status: {status}\n\n"
    if oq2:
        head += f"Owner answer (efv2026 OQ2): **{oq2}. a recorded answer**\n\n"
    return head + "---\n\n## 0. body\n\nOwner answer (efv2026 OQ2): C, below the rule\n"


def _commit(repo: Path, surr: str | None, efv: str | None, msg: str) -> str:
    for rel, text in ((SURR, surr), (EFV, efv)):
        p = repo / rel
        if text is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """A scratch repository with one commit per state the tests read:
    draft (both gates DRAFT), one (surrogate REGISTERED, OQ2 A; EFV DRAFT),
    one_b (surrogate REGISTERED, OQ2 B; EFV DRAFT), two (both REGISTERED, OQ2 B),
    no_answer (surrogate REGISTERED with no OQ2 line)."""
    root = tmp_path_factory.mktemp("surrogate_repo")
    (root / "docs" / "efv-v2").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    shas = {
        "draft": _commit(root, _doc("DRAFT", "B"), _doc("DRAFT"), "draft"),
        "one": _commit(root, _doc("REGISTERED", "A"), _doc("DRAFT"), "one"),
        "no_answer": _commit(root, _doc("REGISTERED"), _doc("DRAFT"), "no answer"),
        "one_b": _commit(root, _doc("REGISTERED", "B"), _doc("DRAFT"), "one b"),
        "two": _commit(root, _doc("REGISTERED", "B"), _doc("REGISTERED"), "two"),
    }
    return root, shas


def _records(path: Path, ids=(), *, recorded=True, reserved_read_date=None) -> None:
    doc = {"looks": [{"id": i, "recorded_at": "2026-12-01T12:00:00Z" if recorded else ""}
                     for i in ids if i != G.OQ6_RELEASE],
           "releases": [{"id": i, "recorded_at": "2028-10-15T12:00:00Z"}
                        for i in ids if i == G.OQ6_RELEASE]}
    if reserved_read_date:
        doc["reserved_read_date"] = reserved_read_date
    (path / G.GATE_RECORD_NAME).write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture()
def env(repo, tmp_path, monkeypatch):
    """The fixture repository as F.ROOT, a scratch data directory (ETA record present,
    no look record) and a scratch module root (no STATUS.md, no .cache)."""
    root, shas = repo
    data = tmp_path / "data"
    data.mkdir()
    (data / G.ETA_EVAL_NAME).write_text(
        json.dumps({G.ETA_LOOK_BLOCK: {"decision": {"verdict": "fixture"}}}),
        encoding="utf-8")
    monkeypatch.setattr(F, "ROOT", root)
    monkeypatch.setattr(G, "DATA_DIR", data)
    monkeypatch.setattr(G, "ROOT", tmp_path)
    return shas, data


# ---------------------------------------------------------------------------
# 2. drafts, fixture ONE, fixture TWO
# ---------------------------------------------------------------------------

def test_a_draft_surrogate_gate_never_opens_the_guard(env):
    shas, _ = env
    sha = shas["draft"]
    assert G.gate_sha_committed_for(sha, SURR) is False
    assert G.gate_header_records(sha, "OQ2") is None
    for V in (2011, 2015, 2019):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(V, gate_sha=sha, purpose="transfer")
    for bad in (None, "", "deadbeef", "0" * 40, sha[:12]):
        assert G.gate_sha_committed_for(bad, SURR) is False
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(2019, gate_sha=bad, purpose="transfer")


def test_fixture_one_opens_the_transfer_read_and_never_r_lv(env):
    shas, _ = env
    sha = shas["one"]
    assert G.gate_sha_committed_for(sha, SURR) is True
    assert G.gate_sha_committed_for(sha, EFV) is False
    G.guard_surrogate_read(2019, gate_sha=sha, purpose="transfer")
    G.guard_surrogate_read(2011, gate_sha=sha, purpose="transfer")
    assert F.gate_sha_committed(sha) is False
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            F.guard_score_request(V, gate_sha=sha)
        for purpose in G.PURPOSES:
            with pytest.raises(F.ReservedFrameError):
                G.guard_surrogate_read(V, gate_sha=sha, purpose=purpose)


def test_fixture_two_r_lv_refuses_though_the_r_lv_guard_accepts_the_sha(env):
    shas, data = env
    sha = shas["two"]
    _records(data, G.RECORD_IDS)
    # the sentence "its REGISTERED sha never opens guard_score_request" is false here
    assert F.gate_sha_committed(sha) is True
    F.guard_score_request(2020, gate_sha=sha)
    assert G.gate_sha_committed_for(sha, SURR) is True
    for V in sorted(F.RESERVED_LV):
        for purpose in G.PURPOSES:
            for s in (sha, shas["one"], shas["one_b"], None, "0" * 40):
                with pytest.raises(F.ReservedFrameError):
                    G.guard_surrogate_read(V, gate_sha=s, look_records=G.RECORD_IDS,
                                           purpose=purpose)


def test_r_lv_refuses_before_any_sha_check(env, monkeypatch):
    def _no(*a, **k):
        raise AssertionError("a sha was checked for an R-LV vintage")
    monkeypatch.setattr(G, "gate_sha_committed_for", _no)
    monkeypatch.setattr(F, "_git_ok", _no)
    for V in sorted(F.RESERVED_LV):
        for purpose in G.PURPOSES + ("not_a_purpose",):
            with pytest.raises(F.ReservedFrameError):
                G.guard_surrogate_read(V, gate_sha=env[0]["two"], purpose=purpose)


def test_the_predicate_is_pure(env):
    shas, _ = env
    before = dict(F._GATE_SHA_MEMO)
    for _ in range(2):
        assert G.gate_sha_committed_for(shas["one"], SURR) is True
    assert F._GATE_SHA_MEMO == before
    with pytest.raises(ValueError):
        G.guard_surrogate_read(2019, gate_sha=shas["one"], purpose="score")


# ---------------------------------------------------------------------------
# 3. the schedule of s2.3, one refusal per test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", [2023, 2024, 2025, 2026])
def test_transfer_refuses_2023_to_2026_always(env, V):
    shas, data = env
    _records(data, G.RECORD_IDS)
    with pytest.raises(F.ReservedFrameError):
        G.guard_surrogate_read(V, gate_sha=shas["two"], look_records=G.RECORD_IDS,
                               purpose="transfer")


@pytest.mark.parametrize("V", [2010, 2027])
def test_transfer_refuses_outside_its_frames(env, V):
    shas, data = env
    _records(data, G.RECORD_IDS)
    with pytest.raises(F.ReservedFrameError):
        G.guard_surrogate_read(V, gate_sha=shas["two"], look_records=G.RECORD_IDS,
                               purpose="transfer")


def test_transfer_2022_refuses_without_look_1(env):
    shas, data = env
    _records(data, (G.LOOK_2, G.LOOK_3, G.OQ6_RELEASE))
    with pytest.raises(F.ReservedFrameError, match=G.LOOK_1):
        G.guard_surrogate_read(2022, gate_sha=shas["one"],
                               look_records=(G.LOOK_2, G.LOOK_3), purpose="transfer")
    _records(data, (G.LOOK_1,))
    G.guard_surrogate_read(2022, gate_sha=shas["one"], look_records=(G.LOOK_1,),
                           purpose="transfer")


def test_only_the_record_file_may_claim_a_record(env):
    shas, data = env
    assert G.look_records() == frozenset()
    with pytest.raises(F.ReservedFrameError, match=G.GATE_RECORD_NAME):
        G.guard_surrogate_read(2022, gate_sha=shas["one"], look_records=(G.LOOK_1,),
                               purpose="transfer")
    _records(data, (G.LOOK_1,), recorded=False)
    assert G.look_records() == frozenset()
    (data / G.GATE_RECORD_NAME).write_text(json.dumps(
        {"looks": [{"id": "rvm_look_9", "recorded_at": "2027-01-01"}],
         "rvm_look_1": {"recorded_at": "2026-12-01"}}), encoding="utf-8")
    assert G.look_records() == frozenset()
    (data / G.GATE_RECORD_NAME).write_text(json.dumps(
        {"looks": {G.LOOK_1: {"recorded_at": "2026-12-01"}}}), encoding="utf-8")
    assert G.look_records() == frozenset({G.LOOK_1})


def test_lv2026_surrogate_refuses_without_look_2(env):
    shas, data = env
    held = (G.LOOK_1, G.LOOK_3, G.OQ6_RELEASE)
    _records(data, held)
    with pytest.raises(F.ReservedFrameError, match=G.LOOK_2):
        G.guard_surrogate_read(2026, gate_sha=shas["one_b"], look_records=held,
                               purpose="lv2026_surrogate")


@pytest.mark.parametrize("which", ["one", "no_answer"])
def test_lv2026_surrogate_refuses_without_oq2_b(env, which):
    shas, data = env
    _records(data, G.RECORD_IDS)
    with pytest.raises(F.ReservedFrameError, match="OQ2"):
        G.guard_surrogate_read(2026, gate_sha=shas[which], look_records=G.RECORD_IDS,
                               purpose="lv2026_surrogate")


def test_lv2026_surrogate_opens_with_look_2_and_oq2_b_only(env):
    shas, data = env
    _records(data, (G.LOOK_2,))
    G.guard_surrogate_read(2026, gate_sha=shas["one_b"], look_records=(G.LOOK_2,),
                           purpose="lv2026_surrogate")
    for V in (2019, 2022, 2025, 2027):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(V, gate_sha=shas["one_b"], look_records=(G.LOOK_2,),
                                   purpose="lv2026_surrogate")


def test_a_2026_read_refuses_without_the_eta_record(env):
    shas, data = env
    _records(data, G.RECORD_IDS)
    (data / G.ETA_EVAL_NAME).unlink()
    assert G.eta_look_recorded() is False
    with pytest.raises(F.ReservedFrameError, match=G.ETA_LOOK_BLOCK):
        G.require_eta_look()
    for purpose in ("lv2026_surrogate", "lv2026_long_run"):
        with pytest.raises(F.ReservedFrameError, match=G.ETA_LOOK_BLOCK):
            G.guard_surrogate_read(2026, gate_sha=shas["two"], look_records=G.RECORD_IDS,
                                   purpose=purpose)
    (data / G.ETA_EVAL_NAME).write_text(json.dumps({G.ETA_LOOK_BLOCK: {}}), encoding="utf-8")
    assert G.eta_look_recorded() is False


@pytest.mark.parametrize("missing", [G.LOOK_1, G.LOOK_2, G.LOOK_3, G.OQ6_RELEASE])
def test_lv2026_long_run_refuses_without_each_record(env, missing):
    shas, data = env
    held = tuple(sorted(G.RECORD_IDS - {missing}))
    _records(data, held)
    with pytest.raises(F.ReservedFrameError, match=missing):
        G.guard_surrogate_read(2026, gate_sha=shas["one"], look_records=held,
                               purpose="lv2026_long_run")


def test_lv2026_long_run_opens_with_every_record_and_only_on_2026(env):
    shas, data = env
    _records(data, G.RECORD_IDS)
    G.guard_surrogate_read(2026, gate_sha=shas["one"], look_records=G.RECORD_IDS,
                           purpose="lv2026_long_run")
    for V in (2019, 2022, 2025):
        with pytest.raises(F.ReservedFrameError):
            G.guard_surrogate_read(V, gate_sha=shas["one"], look_records=G.RECORD_IDS,
                                   purpose="lv2026_long_run")


def test_header_answers_read_only_the_header():
    assert G.header_answer(_doc("REGISTERED", "B"), "OQ2") == "B"
    assert G.header_answer(_doc("REGISTERED"), "OQ2") is None
    assert G.header_answer(_doc("REGISTERED", "A"), "OQ6") is None
    two = "Owner answer (efv2026 OQ2): A\nOwner answer at registration (efv2026 OQ2): B\n"
    assert G.header_answer(two, "OQ2") is None
    assert G.header_answer("Owner answer at draft commit (efv2026 OQ1): A. Own gate\n",
                           "OQ1") == "A"
    assert G.header_answer(None, "OQ2") is None


# ---------------------------------------------------------------------------
# 4. withhold_reserved_vm refuses, never drops
# ---------------------------------------------------------------------------

def _row(key, V, debut=None, **kw):
    return dict(player_key=key, vintage=V, debut_date=debut, **kw)


def test_withhold_refuses_without_the_owning_record(env):
    _, data = env
    rows = [_row("a", 2022, "2025-06-01"), _row("b", 2022, "2025-08-01"),
            _row("c", 2022, "2023-05-01"), _row("d", 2022, None),
            _row("e", 2022, "2026-05-01")]
    with pytest.raises(F.ReservedFrameError, match=r"per cohort 2025: 2\)"):
        G.withhold_reserved_vm(rows, look_records=(), purpose="transfer")
    _records(data, (G.LOOK_1,))
    out, released = G.withhold_reserved_vm(rows, look_records=(G.LOOK_1,),
                                           purpose="transfer")
    assert [r["player_key"] for r in out] == ["a", "b", "c", "d", "e"]
    assert released == {2025: 2}
    for r in out[:2]:
        assert r["status"] == G.RESERVED_VM_STATUS and r["mlb_stat_read"] is False
        assert r["release_record"] == G.LOOK_1
    assert "status" not in out[2] and "status" not in rows[0]


def test_withhold_counts_every_cohort_it_refuses(env):
    rows = [_row("a", 2026, "2026-07-01"), _row("b", 2026, "2027-06-01"),
            _row("c", 2026, "2028-06-01"), _row("d", 2026, "2029-06-01"),
            _row("e", 2026, "2030-06-01"), _row("f", 2026, "2028-07-01")]
    with pytest.raises(F.ReservedFrameError) as exc:
        G.withhold_reserved_vm(rows, look_records=(), purpose="lv2026_long_run")
    assert "5 in-window" in str(exc.value)
    assert "2026: 1, 2027: 1, 2028: 2, 2029: 1" in str(exc.value)


def test_withhold_keeps_event_only_with_the_records(env):
    _, data = env
    _records(data, G.RECORD_IDS)
    rows = [_row("a", 2026, "2026-07-01"), _row("b", 2026, "2027-06-01"),
            _row("c", 2026, "2028-06-01"), _row("d", 2026, None)]
    out, released = G.withhold_reserved_vm(rows, look_records=G.RECORD_IDS,
                                           purpose="lv2026_long_run")
    assert len(out) == len(rows) and released == {2026: 1, 2027: 1, 2028: 1}
    assert all(r["label_released"] is True for r in out[:3])
    assert out[2]["release_record"] == G.OQ6_RELEASE
    # the surrogate read of lv_2026 takes season 2026 only: a 2027 debut is outside it
    _records(data, (G.LOOK_2,))
    out, released = G.withhold_reserved_vm(rows, look_records=(G.LOOK_2,),
                                           purpose="lv2026_surrogate")
    assert released == {2026: 1} and "status" not in out[1]
    with pytest.raises(F.ReservedFrameError):
        G.withhold_reserved_vm(rows[:1], look_records=(), purpose="lv2026_surrogate")


def test_withhold_refuses_r_lv_rows_and_unknown_purposes(env):
    with pytest.raises(F.ReservedFrameError):
        G.withhold_reserved_vm([_row("a", 2020, None)], purpose="transfer")
    with pytest.raises(ValueError):
        G.withhold_reserved_vm([], purpose="score")


# ---------------------------------------------------------------------------
# 5. blocked days
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day", sorted(G.LOOK_DAYS))
def test_blocked_on_the_registered_look_days(env, day):
    with pytest.raises(G.BlockedDayError, match="look day"):
        G.blocked_day(day)


def test_blocked_on_the_reserved_read_day(env, tmp_path):
    _, data = env
    # no record file and no STATUS.md: the PROGRAM.md date stands
    assert G.reserved_read_days() == {G.RESERVED_READ_DEFAULT}
    with pytest.raises(G.BlockedDayError, match="reserved-read"):
        G.blocked_day(G.RESERVED_READ_DEFAULT)
    (tmp_path / "docs" / "efv-v2").mkdir(parents=True)
    (tmp_path / G.STATUS_DOC).write_text(
        "Decision EW2-6 (2026-10-08) replaced the 2026-12-01 reserved read with a "
        "same-day backtest.\n", encoding="utf-8")
    assert G.reserved_read_days() == {"2026-10-08", "2026-12-01"}
    _records(data, (G.LOOK_1,), reserved_read_date="2026-12-03")
    assert G.reserved_read_days() == {"2026-12-03", "2026-12-01"}
    with pytest.raises(G.BlockedDayError):
        G.blocked_day("2026-12-03")
    G.blocked_day("2026-12-04")


def test_the_real_status_doc_names_the_reserved_read(monkeypatch, tmp_path):
    if not (ROOT / G.STATUS_DOC).exists():
        pytest.skip("STATUS.md absent")
    monkeypatch.setattr(G, "DATA_DIR", tmp_path)
    days = G.reserved_read_days()
    assert G.RESERVED_READ_DEFAULT in days and "2026-10-08" in days


def test_blocked_while_another_gate_s_look_marker_exists(env, tmp_path):
    G.blocked_day("2026-10-10")
    own = tmp_path / ".cache" / G.OWN_CACHE_DIR
    own.mkdir(parents=True)
    (own / G.LOOK_MARKER).write_text("{}", encoding="utf-8")
    G.blocked_day("2026-10-10")
    other = tmp_path / ".cache" / "dvm_difficulty"
    other.mkdir()
    (other / G.LOOK_MARKER).write_text("{}", encoding="utf-8")
    with pytest.raises(G.BlockedDayError, match="dvm_difficulty"):
        G.blocked_day("2026-10-10")


# ---------------------------------------------------------------------------
# 6. the DS-03 pattern on every surrogate module
# ---------------------------------------------------------------------------

#: DS-03's outcome tokens (test_efv_identity._FORBIDDEN): none may appear in a function
#: on the identity path.
_FORBIDDEN = re.compile(
    r"debut|career|(^|_)war($|_)|mlb_first|reached|(^|_)label|(^|_)w3|(^|_)r3|"
    r"mlbam_id|birth|all_sports|player_index|sport1|first_mlb|outcome")
_OUTCOME_MODULES = {"efv_labels", "war_source", "ewar", "stats", "source_backtest",
                    "advancement_pace_export", "efv_model", "efv_v2_stat"}
_IDENTITY_NAMES = {"efv_identity", "resolve_record", "build_index", "resolve_name"}
SURROGATE_MODULES = sorted(p.name for p in ROOT.glob("efv_surrogate*.py"))


def _docstrings(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _tokens(node, docs):
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            yield n.id
        elif isinstance(n, ast.Attribute):
            yield n.attr
        elif isinstance(n, ast.arg):
            yield n.arg
        elif isinstance(n, ast.keyword) and n.arg:
            yield n.arg
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            yield n.value


def test_the_guard_module_is_scanned():
    assert "efv_surrogate_guard.py" in SURROGATE_MODULES


@pytest.mark.parametrize("mod", SURROGATE_MODULES)
def test_surrogate_modules_never_call_the_r_lv_guard(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            assert n.id != "guard_score_request", (mod, n.lineno)
        elif isinstance(n, ast.Attribute):
            assert n.attr != "guard_score_request", (mod, n.lineno)
        elif isinstance(n, ast.alias):
            assert n.name != "guard_score_request", mod
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and len(n.value) < 40:
            assert "guard_score_request" not in n.value, (mod, n.lineno)


@pytest.mark.parametrize("mod", SURROGATE_MODULES)
def test_surrogate_modules_import_no_outcome_module(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & _OUTCOME_MODULES, (mod, imported & _OUTCOME_MODULES)


@pytest.mark.parametrize("mod", SURROGATE_MODULES)
def test_the_identity_path_reads_no_debut_or_mlb_column(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    aliases = set(_IDENTITY_NAMES)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            aliases |= {a.asname or a.name for a in n.names if a.name == "efv_identity"}
        elif isinstance(n, ast.ImportFrom) and n.module == "efv_identity":
            aliases |= {a.asname or a.name for a in n.names}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        toks = list(_tokens(fn, docs))
        if not set(toks) & aliases:
            continue
        for tok in toks:
            assert not _FORBIDDEN.search(tok.lower()), (mod, fn.name, tok)
            assert tok != "MLB", (mod, fn.name)
