# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Publish hygiene for the /betting/ payload, three defects pinned 2026-08-16.

 1. THE PAYLOAD PUBLISHED THE BUILD BOX'S OS USERNAME. Four fields on
    data/betting.json (three of them repeated on the preview slice) carried
    absolute Windows paths verbatim: status.feed_health.source,
    record_storage.authoritative_path, record_storage.derived_path and
    record_chain_anchor.source. A path on a public artifact only ever exists to
    say which file inside the checkout answered, so every published path now
    rides through betting_export._public_path and the whole serialized payload
    is scanned here for anything absolute.

 2. THE CHAIN REWRITE CHECK PASSED WITHOUT BEING ABLE TO DETECT A REWRITE.
    With no durable anchor, read_published_chain fell back to the git-tracked
    betting.json, whose committed chain_sha is genesis, and
    chain_extends(None, rows) is True by construction. The record_storage
    blocker's chain half therefore reported itself open on every production
    build while it could not catch anything. It now fails CLOSED, with the
    reason named, whenever the record already holds rows and no trustworthy
    previous value exists.

 3. THREE SURFACES EACH DERIVED THEIR OWN VERDICT WORD. status.model was
    hardcoded in build(), the record label hardcoded "unvalidated" in its
    sentence, and the registry's own verdict for betting_game_prob reached the
    page not at all. model_verdict is the single source now, and the payload
    carries both words plus the sentence explaining them.

Every test here is mutation-provable; the mutation each one catches is named
in its docstring.
"""
from __future__ import annotations

import json
import re

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")


# ---------------------------------------------------------------------------
# the payload, built in memory once for the module
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def built_payload(tmp_path_factory):
    """build(write=False) writes neither payload file, but bi.write_status()
    inside it writes data/betting_status.json unconditionally, so that one
    path is pointed at tmp for the duration. Everything else reads the real
    checkout, which is the point: the scan below has to see the paths the
    real builders publish."""
    tmp = tmp_path_factory.mktemp("hygiene")
    mp = pytest.MonkeyPatch()
    mp.setattr(bi, "STATUS_PATH", tmp / "betting_status.json")
    try:
        yield be.build(write=False)
    finally:
        mp.undo()


# The five shapes an absolute path takes on the three platforms this project
# has ever built on. The drive-letter forward-slash pattern excludes "://" so
# a URL scheme ("https://...") is not a false positive.
ABS_PATH_PATTERNS = (
    r"[A-Za-z]:\\",      # windows drive, backslash (matches the JSON-escaped form too)
    r"[A-Za-z]:/(?!/)",  # windows drive, forward slash, not a URL scheme
    r"/home/",           # linux home
    r"/Users/",          # macos home
    r"AppData",          # windows profile dir, the tell even in a relative form
)


def _abs_path_hits(text: str) -> list[str]:
    hits = []
    for pat in ABS_PATH_PATTERNS:
        for m in re.finditer(pat, text):
            # forty characters of context so a failure names the leaking field
            hits.append(text[max(0, m.start() - 20):m.end() + 40])
    return hits


# ---------------------------------------------------------------------------
# 1. no absolute path anywhere in the serialized payload
# ---------------------------------------------------------------------------
def test_the_payload_contains_no_absolute_filesystem_path(built_payload):
    """The whole payload, serialized, against every absolute-path shape.

    Scanning the serialization rather than the four known fields is
    deliberate: the defect was never one field, it was that ANY builder could
    reach for str(SOME_PATH) and land it on a public artifact. A fifth leak
    site added tomorrow fails this test the same day.

    MUTATION: in betting_export.record_storage, change
    `"authoritative_path": _public_path(RECORD_JSONL if jsonl else RECORD_PATH)`
    back to `str(...)`. The build box's absolute path (username included)
    reappears in the payload and this test fails on the C:\\ pattern.
    """
    txt = json.dumps(built_payload)
    hits = _abs_path_hits(txt)
    assert not hits, (
        "the payload published an absolute filesystem path; every published "
        f"path must ride through _public_path. Leaks: {hits[:5]}")


def test_the_published_paths_are_checkout_relative_and_say_so(built_payload):
    """The four repaired fields, by name, so a leak that somehow dodges the
    broad scan still has a witness, and so the path_basis contract rides the
    block that carries the paths.

    MUTATION: same as the broad scan; additionally, deleting `path_basis`
    from record_storage fails here and nowhere else.
    """
    store = built_payload["record_storage"]
    assert store["authoritative_path"] in (".cache/betting/record.jsonl",
                                           "data/betting_record.json")
    assert store["derived_path"] == "data/betting_record.json"
    assert store["path_basis"] == "relative to the site checkout root"
    assert built_payload["status"]["feed_health"]["source"] == ".cache/odds"
    anchor_src = built_payload["record_chain_anchor"]["source"]
    assert not _abs_path_hits(anchor_src)


# ---------------------------------------------------------------------------
# 2. the chain rewrite check fails closed
# ---------------------------------------------------------------------------
ROW = {"bet_id": "aaaa1111bbbb2222", "slate_date": "2026-08-15",
       "market": "h2h", "side": "home", "point": None,
       "book": "draftkings", "odds_at_post": -120, "stake_units": 1.0}

HEALTH = {"n_slates": 0, "n_slates_with_close": 0, "window_days": 14,
          "diagnosis": "fixture"}


def test_a_nonempty_record_with_no_anchor_closes_the_chain_half(tmp_path, monkeypatch):
    """The vacuous pass, pinned. A durable record holding a row, no anchor
    file, and a previous chain value of None used to leave record_storage open
    because chain_extends(None, rows) is True by construction. That state must
    read CLOSED, with the reason naming the missing anchor, because an open
    blocker that cannot detect the thing it blocks is a lie about the record.

    MUTATION: in betting_export.record_publish_blockers, revert
    `store_open = bool(store["durable"] and chain_ok and not anchor_closed)`
    to `bool(store["durable"] and chain_ok)`. The blocker reads open again and
    both asserts below fail.
    """
    jsonl = tmp_path / "record.jsonl"
    monkeypatch.setattr(be, "RECORD_JSONL", jsonl)
    monkeypatch.setattr(be, "RECORD_PATH", tmp_path / "betting_record.json")
    monkeypatch.setattr(be, "PUBLISHED_CHAIN_PATH", tmp_path / "published_chain.json")
    be.write_record([ROW], path=jsonl)

    bl = be.record_publish_blockers(payload={"slate_date": None, "status": {}},
                                    rows=None, evald={}, health=HEALTH,
                                    settlement={}, published_chain_sha=None)
    rs = next(b for b in bl if b["id"] == "record_storage")
    assert rs["open"] is False, (
        "a non-empty record with no durable anchor and no usable previous "
        "chain value passed the rewrite check vacuously")
    assert rs["have"]["chain_check_armed"] is False
    assert "no durable chain anchor" in rs["reason"]
    assert "fail-closed" in rs["reason"]


def test_the_anchor_report_says_unarmed_for_the_same_state(tmp_path, monkeypatch):
    """read_published_chain and the blocker share chain_anchor_closed_reason,
    so the payload's record_chain_anchor block cannot claim armed while the
    blocker decides vacuous. Same fixture state, other reader.

    MUTATION: reverting the fallback in read_published_chain (returning the
    old four-key dict with no armed field) fails the `armed is False` assert.
    """
    jsonl = tmp_path / "record.jsonl"
    monkeypatch.setattr(be, "RECORD_JSONL", jsonl)
    monkeypatch.setattr(be, "RECORD_PATH", tmp_path / "betting_record.json")
    monkeypatch.setattr(be, "PUBLISHED_CHAIN_PATH", tmp_path / "published_chain.json")
    be.write_record([ROW], path=jsonl)

    anchor = be.read_published_chain()
    assert anchor["durable"] is False
    assert anchor["armed"] is False
    assert "no durable chain anchor" in anchor["unarmed_reason"]


def test_an_empty_record_keeps_genesis_legitimate(tmp_path, monkeypatch):
    """The half that must NOT change. On an empty record there is no history a
    rewrite could destroy, so genesis-or-None stays a pass; failing closed
    there would deadlock the first build of every fresh box.

    MUTATION: over-tightening chain_anchor_closed_reason to fire on an empty
    record (dropping its `if not rows` early return) fails this.
    """
    jsonl = tmp_path / "record.jsonl"
    jsonl.touch()
    monkeypatch.setattr(be, "RECORD_JSONL", jsonl)
    monkeypatch.setattr(be, "RECORD_PATH", tmp_path / "betting_record.json")
    monkeypatch.setattr(be, "PUBLISHED_CHAIN_PATH", tmp_path / "published_chain.json")

    bl = be.record_publish_blockers(payload={"slate_date": None, "status": {}},
                                    rows=None, evald={}, health=HEALTH,
                                    settlement={}, published_chain_sha=None)
    rs = next(b for b in bl if b["id"] == "record_storage")
    assert rs["open"] is True
    assert rs["have"]["chain_check_armed"] is True


def test_a_durable_genesis_anchor_still_arms_an_append_from_empty():
    """A genesis value the DURABLE anchor asserted is a real claim ("the
    record was empty when last published") and an append from it verifies, so
    it must stay armed. Only the fabricated genesis of the git-tracked
    fallback is vacuous."""
    assert be.chain_anchor_closed_reason(
        {"chain_sha": be.CHAIN_GENESIS, "durable": True}, [ROW]) is None
    assert be.chain_anchor_closed_reason(
        {"chain_sha": be.chain_sha([ROW]), "durable": False}, [ROW]) is None
    assert be.chain_anchor_closed_reason(
        {"chain_sha": be.CHAIN_GENESIS, "durable": False}, [ROW]) is not None
    assert be.chain_anchor_closed_reason(
        {"chain_sha": None, "durable": False}, []) is None


# ---------------------------------------------------------------------------
# 3. the verdict speaks from one function
# ---------------------------------------------------------------------------
REG_FIXTURE = {"models": [{"model_id": "betting_game_prob",
                           "verdict": "provisional"}]}


def test_model_verdict_composes_gate_state_from_the_eval_gates():
    """gate_state is the eval artifact's derivation, both halves: validated
    AND a measured min_edge. "All gates open" with a null min_edge is a
    contradiction resolved the safe way.

    MUTATION: dropping `and evald.get("min_edge") is not None` from
    model_verdict flips the contradiction case to "validated" and this fails.
    """
    closed = be.model_verdict({}, registry=REG_FIXTURE)
    assert closed["gate_state"] == "unvalidated"
    opened = be.model_verdict({"validated": True, "min_edge": 0.031},
                              registry=REG_FIXTURE)
    assert opened["gate_state"] == "validated"
    contradiction = be.model_verdict({"validated": True, "min_edge": None},
                                     registry=REG_FIXTURE)
    assert contradiction["gate_state"] == "unvalidated"


def test_model_verdict_reads_the_registry_word_rather_than_assuming_it():
    """registry_verdict is lifted from the betting_game_prob row, whatever it
    says, and a missing row degrades to None rather than to a guessed word.

    MUTATION: hardcoding `registry_verdict = "provisional"` in model_verdict
    fails on the "validated" fixture and on the missing-row fixture.
    """
    flipped = {"models": [{"model_id": "betting_game_prob",
                           "verdict": "validated"}]}
    assert be.model_verdict({}, registry=flipped)["registry_verdict"] == "validated"
    assert be.model_verdict({}, registry={"models": []})["registry_verdict"] is None
    mv = be.model_verdict({}, registry=REG_FIXTURE)
    assert mv["registry_verdict"] == "provisional"
    # the sentence explains BOTH words, not one of them
    assert "unvalidated" in mv["sentence"]
    assert "provisional" in mv["sentence"]


def test_the_status_block_speaks_from_model_verdict_not_from_a_copy(tmp_path, monkeypatch):
    """THE SEAM, proven by substitution: stub model_verdict and every verdict
    surface on the payload must carry the stub's words, because a call site
    that kept a private copy of the enum would keep publishing it no matter
    what the single source says.

    MUTATION: in build(), revert `"model": verdict["gate_state"]` to the old
    hardcoded `"validated" if validated else "unvalidated"`. status.model then
    reads "unvalidated" while the stub says otherwise, and this fails.
    """
    stub = {"gate_state": "stub-state", "registry_verdict": "stub-verdict",
            "sentence": "stub sentence."}
    monkeypatch.setattr(be, "model_verdict", lambda evald, **kw: dict(stub))
    monkeypatch.setattr(bi, "STATUS_PATH", tmp_path / "betting_status.json")
    p = be.build(write=False)
    assert p["status"]["model"] == "stub-state"
    assert p["status"]["model_registry_verdict"] == "stub-verdict"
    assert p["status"]["model_verdict_sentence"] == "stub sentence."


def test_the_payload_carries_both_words_and_they_agree_with_the_source(built_payload):
    """The real build, unstubbed: the machine enum stays the machine enum, the
    registry word rides beside it, and both match what model_verdict says for
    the same inputs. Today that is gates closed and a provisional registry
    row, and this asserts agreement rather than pinning today's words so the
    day either flips the test does not rot."""
    status = built_payload["status"]
    assert status["model"] in ("validated", "unvalidated")
    evald = be._load("betting_model_eval.json") or {}
    mv = be.model_verdict(evald)
    assert status["model"] == mv["gate_state"]
    assert status["model_registry_verdict"] == mv["registry_verdict"]
    assert status["model_verdict_sentence"] == mv["sentence"]
    # the record label uses the same word, not a private copy
    label = built_payload["record_label"]
    if label is not None:
        assert f"The model is {mv['gate_state']}:" in label
