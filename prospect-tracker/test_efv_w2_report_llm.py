# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the report-extraction preparation and loader (efv_w2_report_llm.py,
EFV4_REPORT_EXTRACT_PREP). Fixtures only: no frame, no database, no label, no model.

1. The schema: twelve fields, the twelve served column names, heads, side nulls.
2. Validation: types, ranges, the enum, side nulls, floor not above ceiling, no extra key.
3. Redaction: the player's name forms, other persons, clubs, affiliates, schools, money,
   picks, ranks and ages go; leagues, countries and Tommy John stay; identity=False is
   the invariance control and keeps names.
4. The corpus: doc_id is the sha256 of the redacted text; carried text shares an id.
5. The controls: invariance documents keep the name and pair to their redacted id;
   shuffle donors are another player of the same side and vintage; ids are opaque and
   seeded.
6. The chunks: 40 documents at most, every document once, controls in their own files.
7. The loader: valid files land keyed by (doc_id, control_id, prompt, model); a rerun
   adds nothing; a differing repeat is a conflict and the first stands; a wrong prompt,
   an unknown chunk, a bad model id reject the file; a bad extraction rejects alone.
8. The columns: a row's documents average, the injury flag is a maximum, controls and
   other models are ignored; writer_minus_stated is a within-group percentile gap.
9. Guards and scans: no reserved or dropped corpus vintage, a reserved row raises, the
   lab registers the arms, no FV-level grouping token, no network import, no em-dash.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_vintage_frame as F
import efv_w2_report_llm as R

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "efv_w2_report_llm.py"
sys.path.insert(0, str(ROOT / "tools"))


def _ok_fields(side="pit", **kw):
    f = {"conviction": 4, "hedge_count": 3, "risk": 2, "injury_mention": "none",
         "makeup": 1, "body_projection": 0, "role_ceiling": 4, "role_floor": 2,
         "reliever_risk": 2 if side == "pit" else None,
         "approach_concern": 1 if side == "hit" else None, "writer_level": 5,
         "arrival": 1}
    f.update(kw)
    return f


# 1. the schema ------------------------------------------------------------------------

def test_schema_has_the_twelve_fields_and_columns():
    s = R.json_schema()
    assert len(s["required"]) == 12 and s["additionalProperties"] is False
    assert set(s["properties"]) == set(R.FIELD_ORDER)
    assert R.COLUMNS == ("txt_conviction", "txt_hedge_count", "txt_risk",
                         "txt_injury_mention", "txt_makeup", "txt_body_projection",
                         "txt_role_ceiling", "txt_role_floor", "txt_reliever_risk",
                         "txt_approach_concern", "txt_writer_minus_stated", "txt_arrival")
    assert {c for c in R.COLUMNS if R.column_head(c) == "time"} == {"txt_arrival",
                                                                    "txt_role_floor"}
    names = {a["name"] for a in R.ARMS}
    assert len(R.ARMS) == 22 and "rpt_reliever_risk_pit" in names
    assert "rpt_reliever_risk_hit" not in names and "rpt_approach_concern_pit" not in names
    for f, p in s["properties"].items():
        assert p["description"]


def test_prompt_rules_and_hash():
    t = R.PROMPT_TEXT
    for must in ("outside knowledge", "Never try to work out who the player is",
                 "Never output a grade the text does not state",
                 "Never predict what happened to the player later"):
        assert must in t
    assert R.PROMPT_SHA == R.prompt_sha256()
    assert R.prompt_sha256(t + " ") != R.PROMPT_SHA
    other = R.json_schema()
    other["required"] = other["required"][:-1]
    assert R.prompt_sha256(t, other) != R.PROMPT_SHA
    assert R.prompt_sha256(t.replace("\n", "\r\n")) == R.PROMPT_SHA


# 2. validation ------------------------------------------------------------------------

def test_valid_extractions_pass():
    assert R.validate_fields(_ok_fields("pit"), "pit") == []
    assert R.validate_fields(_ok_fields("hit"), "hit") == []
    assert R.validate_fields(_ok_fields("hit", role_floor=None), "hit") == []


@pytest.mark.parametrize("side,kw,needle", [
    ("pit", {"conviction": 6}, "outside"),
    ("pit", {"conviction": True}, "not an integer"),
    ("pit", {"risk": 2.5}, "not an integer"),
    ("pit", {"injury_mention": "ankle"}, "not in"),
    ("pit", {"approach_concern": 1}, "must be null"),
    ("hit", {"reliever_risk": 3}, "must be null"),
    ("pit", {"reliever_risk": None}, "is null"),
    ("pit", {"role_floor": 5, "role_ceiling": 3}, "above role_ceiling"),
    ("pit", {"arrival": -3}, "outside"),
    ("pit", {"extra": 1}, "extra keys"),
])
def test_invalid_extractions_fail(side, kw, needle):
    errs = R.validate_fields(_ok_fields(side, **kw), side)
    assert any(needle in e for e in errs), errs


def test_missing_field_fails():
    f = _ok_fields()
    del f["makeup"]
    assert "missing makeup" in R.validate_fields(f, "pit")
    assert R.validate_fields([], "pit") == ["fields is not an object"]


# 3. redaction -------------------------------------------------------------------------

LEX = R.Lexicon(persons={R._norm("Jeff Samardzija"), R._norm("Albert Almora Jr.")},
                schools={"Vanderbilt"}, places={"Altoona"})
TEXT = ("The Pirates drafted Jordan Smith 9th overall out of Vanderbilt and gave him "
        "$2.5 million. Smith's fastball sits 94. He was traded to Boston for Jeff "
        "Samardzija and Albert Almora, then reached Double-A Altoona at age 21, a "
        "19-year-old in the Texas League. He is the No. 3 prospect in the Pirates' "
        "system. Tommy John surgery in the Dominican Republic cost him a year; Altoona "
        "fans saw him at Arizona State.")


def test_redaction_removes_identity():
    red, c = R.redact(TEXT, player_names=["Jordan Smith"], lexicon=LEX)
    for gone in ("Jordan", "Smith", "Pirates", "Boston", "Samardzija", "Almora",
                 "Vanderbilt", "Altoona", "2.5", "9th", "21", "19-year", "No. 3",
                 "Arizona State"):
        assert gone not in red, (gone, red)
    for kept in ("Texas League", "Tommy John", "Dominican Republic", "fastball sits 94",
                 "[PLAYER]'s fastball", "[CLUB]'"):
        assert kept in red, (kept, red)
    for k in ("player", "person", "club", "school", "affiliate", "money", "pick", "rank",
              "age"):
        assert c.get(k, 0) >= 1, (k, c)


def test_identity_off_keeps_names():
    raw, c = R.redact(TEXT, player_names=["Jordan Smith"], lexicon=LEX, identity=False)
    assert "Jordan Smith" in raw and "Pirates" in raw and c == {}


def test_name_forms_tails_and_particles():
    f = R.name_forms(["Adam Brett Walker", "Oscar De La Cruz", "Ronald Acuña Jr."])
    for want in ("Adam Brett Walker", "Brett Walker", "Walker", "De la Cruz",
                 "de la Cruz", "Cruz", "Acuna", "Acuña"):
        assert want in f, want
    for never in ("Adam", "Oscar", "Ronald", "de", "Jr.", "Acuna Jr."):
        assert never not in f, never
    assert f == sorted(f, key=lambda s: (-len(s), s))


def test_lone_first_name_and_common_words_survive():
    red, _ = R.redact("In story time, Trevor Story told a long story to Trevor.",
                      player_names=["Trevor Story"])
    assert red == "In story time, [PLAYER] told a long story to Trevor."


def test_drop_common_words_and_places():
    kept = R.drop_common_words(["Mobile", "Bradley", "Vanderbilt", "York", "Notre Dame"],
                               ["he is mobile, very mobile and mobile"],
                               frozenset({"Bradley"}))
    assert kept == ["Vanderbilt", "Notre Dame"]
    places = R.level_places(["He reached Double-A Altoona. Later High-A Lake Elsinore.",
                             "Double-A Reading.", "reading reading reading",
                             "Triple-A Pacific Coast and Class A Short-Season Lowell"])
    assert "Altoona" in places and "Lake Elsinore" in places and "Lowell" in places
    assert "Reading" not in places and "Pacific Coast" not in places


# 4 to 6. the corpus, controls and chunks ----------------------------------------------

def _docs():
    out = []
    for side in ("hit", "pit"):
        for V in (2014, 2015):
            for i in range(6):
                pk = f"{side}_{V}_{i}"
                out.append({"side": side, "vintage": V, "player_key": pk,
                            "source": "mlb_pipeline", "date": f"{V}-02-01",
                            "clean": f"Player{i} Name{side}{V} has a plus arm and "
                                     f"Name{side}{V} could start. Text {side} {V} {i}."})
    # a carried identical document for a second vintage row
    out.append(dict(out[0], vintage=2015, player_key="hit_2014_0"))
    return out


def _names(docs):
    return {d["player_key"]: [f"Player{d['player_key'][-1]} Name{d['side']}{d['vintage']}"]
            for d in docs}


def test_corpus_ids_and_dedupe():
    docs = _docs()
    names = _names(docs)
    names["hit_2014_0"] = ["Player0 Namehit2014"]
    c = R.build_corpus(docs, names, R.Lexicon())
    for did, d in c["documents"].items():
        assert did == hashlib.sha256(d["text"].encode("utf-8")).hexdigest()
        assert "[PLAYER]" in d["text"]
    assert len(c["rows"]) == len(docs) and len(c["documents"]) == len(docs) - 1
    assert c["rows"][0]["doc_id"] == c["rows"][-1]["doc_id"]
    assert c["residual"] == []
    cov = R.coverage(c)
    assert cov["hit:2015"]["row_documents"] == 7 and cov["hit:2015"]["unique_documents"] == 7


def test_controls_and_chunks(tmp_path):
    docs = _docs()[:-1]
    names = _names(docs)
    c = R.build_corpus(docs, names, R.Lexicon())
    ctl = R.build_controls(docs, c, names, R.Lexicon(), n=8, seed=7)
    again = R.build_controls(docs, c, names, R.Lexicon(), n=8, seed=7)
    assert ctl == again
    assert len(ctl["invariance"]) == 8 and len(ctl["shuffle"]) == 8
    for x in ctl["invariance"]:
        assert names[x["player_key"]][0] in x["text"]
        assert x["paired_doc_id"] in c["documents"] and x["doc_id"] != x["paired_doc_id"]
    for x in ctl["shuffle"]:
        assert x["donor_player_key"] != x["player_key"]
        assert x["donor_player_key"].startswith(f"{x['side']}_{x['vintage']}_")
        assert x["text"] == c["documents"][x["donor_doc_id"]]["text"]
    ids = [x["control_id"] for x in ctl["invariance"] + ctl["shuffle"]]
    assert len(set(ids)) == len(ids) and all(i.startswith("c") and len(i) == 17 for i in ids)

    chunks = R.chunk_payloads(c, ctl, size=5)
    main = [d for n, o in chunks.items() if n.startswith("chunk_") for d in o["documents"]]
    ctrl = [d for n, o in chunks.items() if n.startswith("control_") for d in o["documents"]]
    assert sorted(d["doc_id"] for d in main) == sorted(c["documents"])
    assert all(set(d) == {"doc_id", "side", "text"} for d in main)
    assert sorted(d["control_id"] for d in ctrl) == sorted(ids)
    assert all(len(o["documents"]) <= 5 and o["prompt_sha256"] == R.PROMPT_SHA
               for o in chunks.values())
    assert R.CHUNK_SIZE == 40

    (tmp_path / "chunks").mkdir()
    (tmp_path / "chunks" / "chunk_9999.json").write_text("{}", encoding="utf-8")
    idx = R.write_extract_files(tmp_path, chunks)
    assert not (tmp_path / "chunks" / "chunk_9999.json").exists()
    assert json.loads((tmp_path / "SCHEMA.json").read_text(encoding="utf-8")) == R.json_schema()
    assert (tmp_path / "PROMPT.md").read_text(encoding="utf-8") == R.PROMPT_TEXT
    assert idx["prompt_sha256"] == R.PROMPT_SHA and sum(idx["chunks"].values()) == len(
        main) + len(ctrl)


# 7. the loader ------------------------------------------------------------------------

def _setup(tmp_path, n=3, control=False):
    cdir = tmp_path / "chunks"
    odir = tmp_path / "out"
    cdir.mkdir(exist_ok=True)
    odir.mkdir(exist_ok=True)
    docs = []
    for i in range(n):
        side = "pit" if i % 2 else "hit"
        d = {"doc_id": hashlib.sha256(f"doc{i}".encode()).hexdigest(), "side": side,
             "text": f"doc{i}"}
        if control:
            d["control_id"] = f"c{i:016d}"
        docs.append(d)
    name = "control_0001" if control else "chunk_0001"
    (cdir / f"{name}.json").write_text(json.dumps(
        {"chunk": name, "prompt_sha256": R.PROMPT_SHA, "documents": docs}), encoding="utf-8")
    return cdir, odir, name, docs


def _out(odir, name, docs, *, model="claude-opus-5-5", prompt=None, mutate=None):
    ex = []
    for d in docs:
        e = {"doc_id": d["doc_id"], "fields": _ok_fields(d["side"])}
        if "control_id" in d:
            e["control_id"] = d["control_id"]
        ex.append(e)
    if mutate:
        mutate(ex)
    (odir / f"{name}.json").write_text(json.dumps(
        {"chunk": name, "prompt_sha256": prompt or R.PROMPT_SHA, "model_id": model,
         "extractions": ex}), encoding="utf-8")


def test_ingest_lands_and_is_idempotent(tmp_path):
    cdir, odir, name, docs = _setup(tmp_path)
    store = tmp_path / "store.jsonl"
    _out(odir, name, docs)
    r = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r["accepted"] == 3 and r["files_rejected"] == {} and r["store_rows"] == 3
    rows = R.read_store(store)
    assert {R.store_key(x) for x in rows} == {(d["doc_id"], "", R.PROMPT_SHA,
                                               "claude-opus-5-5") for d in docs}
    before = store.read_bytes()
    r2 = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r2["accepted"] == 0 and r2["already_stored"] == 3 and r2["conflicts"] == 0
    assert store.read_bytes() == before

    def change(ex):
        ex[0]["fields"]["risk"] = 5
    _out(odir, name, docs, mutate=change)
    r3 = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r3["conflicts"] == 1 and store.read_bytes() == before

    _out(odir, name, docs, model="claude-sonnet-5-5")
    r4 = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r4["accepted"] == 3 and r4["store_rows"] == 6


def test_ingest_rejects(tmp_path):
    cdir, odir, name, docs = _setup(tmp_path)
    store = tmp_path / "store.jsonl"
    _out(odir, name, docs, prompt="0" * 64)
    r = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert "prompt" in r["files_rejected"][f"{name}.json"] and not store.exists()
    _out(odir, name, docs, model="Opus 5!")
    assert "model_id" in R.ingest(odir, chunks_dir=cdir, store_path=store)[
        "files_rejected"][f"{name}.json"]
    (odir / f"{name}.json").unlink()
    _out(odir, "chunk_0002", docs)
    assert "no chunk" in R.ingest(odir, chunks_dir=cdir, store_path=store)[
        "files_rejected"]["chunk_0002.json"]
    (odir / "chunk_0002.json").unlink()

    def spoil(ex):
        ex[0]["fields"]["conviction"] = 9
        ex[1]["doc_id"] = "f" * 64
        ex.pop()
    _out(odir, name, docs, mutate=spoil)
    r = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r["accepted"] == 0 and len(r["invalid"][f"{name}.json"]) == 1
    assert r["unknown_documents"][f"{name}.json"] == ["f" * 64]
    assert r["missing_documents"][f"{name}.json"] == 3


def test_ingest_control_ids(tmp_path):
    cdir, odir, name, docs = _setup(tmp_path, control=True)
    store = tmp_path / "store.jsonl"
    _out(odir, name, docs)
    r = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r["accepted"] == 3
    assert all(x["control_id"] for x in R.read_store(store))

    def drop_cid(ex):
        for e in ex:
            e.pop("control_id")
    store.unlink()
    _out(odir, name, docs, mutate=drop_cid)
    r = R.ingest(odir, chunks_dir=cdir, store_path=store)
    assert r["accepted"] == 0 and len(r["unknown_documents"][f"{name}.json"]) == 3


# 8. the columns -----------------------------------------------------------------------

def test_row_fields_average_and_filter():
    m = [{"side": "pit", "vintage": 2019, "player_key": "p", "source": "mlb_pipeline",
          "doc_id": "a"},
         {"side": "pit", "vintage": 2019, "player_key": "p", "source": "fangraphs",
          "doc_id": "b"},
         {"side": "hit", "vintage": 2018, "player_key": "h", "source": "mlb_pipeline",
          "doc_id": "c"}]

    def rec(did, f, model="claude-opus-5-5", cid=None):
        return {"doc_id": did, "control_id": cid, "prompt_sha256": R.PROMPT_SHA,
                "model_id": model, "fields": f}
    store = [rec("a", _ok_fields("pit", risk=1, role_floor=None, injury_mention="elbow")),
             rec("b", _ok_fields("pit", risk=4, role_floor=3)),
             rec("c", _ok_fields("hit")),
             rec("c", _ok_fields("hit", risk=5), model="other-model"),
             rec("a", _ok_fields("pit", risk=5), cid="c" + "0" * 16)]
    out = R.row_fields(m, store, model_id="claude-opus-5-5")
    p = out[("pit", 2019, "p")]
    assert p["risk"] == 2.5 and p["role_floor"] == 3.0 and p["injury_mention"] == 1.0
    assert out[("hit", 2018, "h")]["risk"] == 2.0
    assert out[("hit", 2018, "h")]["reliever_risk"] is None


def test_writer_minus_stated_is_a_within_group_gap():
    wl = [1, 2, 3, None, 3, 1]
    fv = [50, 45, 40, 55, 40, 45]
    g = [("pit", 2015)] * 4 + [("hit", 2015)] * 2
    d = R.writer_minus_stated(wl, fv, g)
    assert np.isnan(d[3])
    assert np.allclose(d[:3], [1 / 3 - 1.0, 0.0, 1.0 - 1 / 3])
    assert np.allclose(d[4:], [0.5, -0.5])


def _frames(rows_by_v):
    """{side: {V: (rows, labels)}} in the efv_v2_assemble shape (labels unused)."""
    out = {"hit": {}, "pit": {}}
    for (side, V), rows in rows_by_v.items():
        out[side][V] = (rows, [{} for _ in rows])
    return out


def _lv_fixture():
    frames = _frames({
        ("pit", 2018): [{"player_key": "a", "asof_date": "2018-03-01",
                         "grades": {R.CONSENSUS_KEY: 50.0}},
                        {"player_key": "b", "asof_date": "2018-03-01",
                         "grades": {R.CONSENSUS_KEY: 45.0}},
                        {"player_key": "c", "asof_date": "2018-03-01",
                         "grades": {R.CONSENSUS_KEY: 40.0}},
                        {"player_key": "late", "asof_date": "2018-03-01",
                         "grades": {R.CONSENSUS_KEY: 40.0}}],
        ("pit", 2019): [{"player_key": "a", "asof_date": "2019-03-01",
                         "grades": {R.CONSENSUS_KEY: 55.0}}]})
    man = [{"side": "pit", "vintage": 2018, "player_key": "a", "source": "mlb_pipeline",
            "date": "2018-02-01", "doc_id": "da"},
           {"side": "pit", "vintage": 2018, "player_key": "b", "source": "mlb_pipeline",
            "date": "2018-02-01", "doc_id": "db"},
           {"side": "pit", "vintage": 2018, "player_key": "late", "source": "mlb_pipeline",
            "date": "2018-04-01", "doc_id": "dl"},
           {"side": "pit", "vintage": 2019, "player_key": "a", "source": "mlb_pipeline",
            "date": "2019-02-01", "doc_id": "da2"}]

    def rec(did, **kw):
        return {"doc_id": did, "control_id": None, "prompt_sha256": R.PROMPT_SHA,
                "model_id": "m-1", "fields": _ok_fields("pit", **kw)}
    store = [rec("da", writer_level=3, risk=1), rec("db", writer_level=6, risk=5),
             rec("dl", writer_level=7), rec("da2", writer_level=4, risk=2)]
    return frames, man, store


def test_lv_values_as_of_and_the_writer_gap():
    frames, man, store = _lv_fixture()
    rec = {}
    v = R.lv_values("pit", frames, manifest_rows=man, store=store, model_id="m-1",
                    receipt=rec)
    assert v[(2018, "c")] is None
    assert v[(2018, "late")] is None
    assert rec["documents_after_asof_dropped"] == 1 and rec["rows_with_document"] == 3
    assert v[(2018, "a")]["txt_risk"] == 1.0 and v[(2018, "b")]["txt_risk"] == 5.0
    assert "txt_approach_concern" not in v[(2018, "a")]
    assert v[(2018, "a")]["txt_writer_minus_stated"] == pytest.approx(0.5 - 1.0)
    assert v[(2018, "b")]["txt_writer_minus_stated"] == pytest.approx(1.0 - 0.5)
    assert v[(2019, "a")]["txt_writer_minus_stated"] == pytest.approx(0.0)
    assert v[(2018, "a")]["_date"] == "2018-02-01"


def test_carried_value_takes_the_latest_dated_on_or_before():
    frames, man, store = _lv_fixture()
    v = R.lv_values("pit", frames, manifest_rows=man, store=store, model_id="m-1")
    assert R.carried_value(v, "a", "2018-12-31")["txt_risk"] == 1.0
    assert R.carried_value(v, "a", "2020-07-01")["txt_risk"] == 2.0
    assert R.carried_value(v, "a", "2018-01-31") is None
    assert R.carried_value(v, "a", None) is None
    assert R.carried_value(v, "zz", "2020-01-01") is None


def test_store_model_id_refuses_mixed_extractors():
    _f, _m, store = _lv_fixture()
    assert R.store_model_id(store) == "m-1"
    with pytest.raises(ValueError):
        R.store_model_id(store + [dict(store[0], model_id="m-2")])


def test_screen_column_is_the_lab_hook(monkeypatch):
    frames, man, store = _lv_fixture()
    monkeypatch.setattr(R, "load_manifest", lambda path=None: {"rows": man})
    monkeypatch.setattr(R, "read_store", lambda path=None: store)
    R._LV_MEMO.clear()
    col = R.screen_column("txt_risk", "pit", frames)
    assert col[(2018, "a")] == 1.0 and col[(2018, "c")] is None
    with pytest.raises(ValueError):
        R.screen_column("txt_approach_concern", "pit", frames)
    R._LV_MEMO.clear()


def test_control_receipt_pairs_donors_and_twins():
    _f, _m, store = _lv_fixture()
    cid1, cid2 = "c" + "1" * 16, "c" + "2" * 16
    store = store + [
        {"doc_id": "da", "control_id": cid1, "prompt_sha256": R.PROMPT_SHA,
         "model_id": "m-1", "fields": _ok_fields("pit", writer_level=3, risk=1)},
        {"doc_id": "raw", "control_id": cid2, "prompt_sha256": R.PROMPT_SHA,
         "model_id": "m-1", "fields": _ok_fields("pit", writer_level=7, risk=2)}]
    man = {"controls": {"shuffle": [{"control_id": cid1, "donor_doc_id": "da",
                                     "side": "pit"}],
                        "invariance": [{"control_id": cid2, "paired_doc_id": "db",
                                        "side": "pit"}]}}
    r = R.control_receipt(man, store, "m-1")
    assert r["shuffle"]["n_pairs"] == 1 and r["shuffle"]["fields"]["risk"]["exact_share"] == 1.0
    inv = r["invariance"]["fields"]
    assert inv["writer_level"]["mean_diff"] == 1.0 and inv["risk"]["mean_diff"] == -3.0


# 9. guards and scans ------------------------------------------------------------------

def test_corpus_vintages_and_reserved_guard():
    assert not set(R.CORPUS_VINTAGES) & set(F.RESERVED_LV)
    assert not set(R.CORPUS_VINTAGES) & {2011, 2012}
    assert max(R.CORPUS_VINTAGES) < min(F.RESERVED_LV)
    row = {"vintage": 2020, "side": "hit", "player_key": "x", "report_sources": []}
    with pytest.raises(F.ReservedFrameError):
        R.row_documents([row], {})


def test_the_lab_registers_the_arms():
    import efv_screen_lab as LAB
    assert LAB.WAVE2_DEV["efv_w2_report_read"] == R.ARM_NAMES
    for a in R.ARMS:
        assert a["kind"] == "column" and a["head"] in LAB.HEADS
        assert a["column"] == {"source": "module", "module": R.MODULE,
                               "attr": "screen_column", "arg": a["field_column"]}
        assert (a["head"] == "timing") == (a["field_column"] in R.TIMING_COLUMNS)
    assert R.STORE_PATH.as_posix().endswith("data/_labs/efv_w2/report_extract.jsonl")
    assert R.MANIFEST_PATH.as_posix().endswith(
        "data/_labs/efv_w2/report_extract_manifest.json")


_BANNED_TOKENS = ("groupby", "tier", "bucket", "stratum", "strata", "by_fv", "fv_band",
                  "fv_bin", "by_consensus", "per_fv", "per_consensus")
_BANNED_IMPORTS = ("urllib", "requests", "http", "anthropic", "socket", "efv_labels",
                   "backtest")


def test_no_fv_level_grouping_no_network_no_dash():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED_TOKENS), name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            for mname in mods:
                assert not any(mname.split(".")[0] == b for b in _BANNED_IMPORTS), mname
        if isinstance(node, ast.Compare) and "fv" in ast.unparse(node).lower():
            assert not any(isinstance(n, ast.Constant) and type(n.value) in (int, float)
                           for n in ast.walk(node)), ast.unparse(node)
    for p in (SRC, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt
