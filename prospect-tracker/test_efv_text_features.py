# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_B2 pins for the text family (SP/efv3/EFV3_PLAN.md s4; LANE_B.md F-B2, F-B3,
F-B12 and the text rule in s3).

1. The builder reads no WAR, debut, label or major league column: its imports are the
   allowed set, its names carry no outcome word, and poisoning every outcome field on
   the input rows leaves every text output unchanged.
2. The window rule: a report dated after the row's window (or before it, or from a
   source that did not publish in it) never enters a row; V 2011 and 2012 return no
   text; an injected later-year sentence drops the report; byte-identical carried
   text is counted.
3. Grade strings, FV tokens, ETA tokens and years never reach the tokenizer.
4. The fold: the vocabulary of fold V holds no token first seen at V; a V-frame player
   in the training rows raises (GATE s4.5); reserved vintages raise everywhere.
5. The DS-03 verdict on report_absent decides which heads are offered.
6. No FV-cell grouping (PROSPECT_ANCHOR_GATE) in the builder or the probe tool.
7. The committed receipt key "text" is for this builder and reads no reserved frame.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_text_features as T
import efv_vintage_frame as F

ROOT = Path(__file__).parent
SRC = ROOT / "efv_text_features.py"
TOOL = ROOT / "tools" / "efv_text_balance.py"
ART = ROOT / "data" / "efv_identity_balance.json"
_ALLOWED_IMPORTS = {"__future__", "hashlib", "json", "re", "sqlite3", "pathlib", "numpy",
                    "sklearn", "efv_vintage_frame"}
_OUTCOME_WORD = re.compile(r"(^|_)(war|fwar|ewar|debut|debuts|reached|w3|r3|l6|label|"
                           r"labels|mlbam|outcome|statline)(_|$)")
_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")

LONG = ("He has a loose, quick swing with natural loft and the barrel control to use "
        "the whole field. The arm plays at shortstop and the hands are soft, though "
        "the range may push him to second base as he fills out. Scouts like the makeup.")


def _row(pk, V, side="hit", real=("mlb_pipeline",), fv=52.5, debut=None):
    lo, hi = F.window_bounds(V, debut)
    return {"player_key": pk, "vintage": V, "side": side, "window": [lo, hi],
            "real_sources": list(real), "grades": {"consensus": fv}, "fv": fv}


def _rep(source, date, text=LONG):
    return {"source": source, "date": date, "text": text}


# ---------------------------------------------------------------------------
# 1. no label, no outcome column
# ---------------------------------------------------------------------------

def _imports(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def _names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.alias):
            yield node.name


def test_imports_are_the_allowed_set():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    assert _imports(tree) <= _ALLOWED_IMPORTS, _imports(tree) - _ALLOWED_IMPORTS


def test_builder_names_no_outcome_column():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for name in _names(tree):
        assert not _OUTCOME_WORD.search(name.lower()), name
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not _OUTCOME_WORD.search(low), node.value
            if "mlb" in low:
                assert low == "mlb_pipeline", node.value


def test_outputs_ignore_every_outcome_field():
    rows = [_row("a", 2016), _row("b", 2016, real=("mlb_pipeline", "fangraphs"))]
    reps = {"a": [_rep("mlb_pipeline", "2016-02-01")],
            "b": [_rep("mlb_pipeline", "2016-02-01"), _rep("fangraphs", "2016-03-01")]}
    clean = T.attach_text(rows, reps)
    poisoned = copy.deepcopy(rows)
    for r in poisoned:
        r.update(war=1e9, fwar=float("nan"), w3=7.0, r3=1.0, reached="reached",
                 debut_date="2016-01-02", mlbam_id=1, record_mlbam_id=2, l6=5.0)
    dirty = T.attach_text(poisoned, reps)
    keys = [k for k in clean[0] if k.startswith("report_")]
    assert keys
    for c, d in zip(clean, dirty):
        assert {k: c[k] for k in keys} == {k: d[k] for k in keys}
    assert clean[1]["report_absent"] == 0.0 and clean[1]["report_sources"]


# ---------------------------------------------------------------------------
# 2. the window rule
# ---------------------------------------------------------------------------

def test_report_after_the_window_never_enters_a_row():
    rows = [_row("a", 2016)]
    reps = {"a": [_rep("mlb_pipeline", "2015-12-31", LONG + " before"),
                  _rep("mlb_pipeline", "2016-03-01", LONG + " inside"),
                  _rep("mlb_pipeline", "2016-06-01", LONG + " after")]}
    out = T.attach_text(rows, reps)[0]
    assert out["report_absent"] == 0.0
    assert out["report_date"] == "2016-03-01"
    assert out["report_len"] == len(LONG + " inside")
    assert [s["date"] for s in out["report_sources"]] == ["2016-03-01"]
    assert "after" not in out["report_text"] and "before" not in out["report_text"]
    # a window cut short at the debut excludes a report after the cut
    cut = _row("a", 2016, debut="2016-02-15")
    out = T.attach_text([cut], reps)[0]
    assert out["report_absent"] == 1.0 and out["report_in_window"] == 0.0
    # a source that did not publish inside the window is not read
    other = _row("a", 2016, real=("fangraphs",))
    assert T.attach_text([other], reps)[0]["report_absent"] == 1.0


def test_dropped_vintages_return_no_text():
    for V in T.DROPPED_VINTAGES:
        rows = [_row("a", V)]
        reps = {"a": [_rep("mlb_pipeline", f"{V}-02-01")]}
        out = T.attach_text(rows, reps)[0]
        assert out["report_absent"] == 1.0 and out["report_text"] is None
        assert out["report_vintage_dropped"] is True
    assert min(T.DROPPED_VINTAGES) == min(F.DEV_VINTAGES)
    assert T.FIRST_TEXT_VINTAGE == max(T.DROPPED_VINTAGES) + 1


def test_injected_later_year_drops_the_report():
    rows = [_row("a", 2016), _row("b", 2016), _row("c", 2016), _row("d", 2016)]
    reps = {"a": [_rep("mlb_pipeline", "2016-02-01", LONG + " He should be ready in 2021.")],
            "b": [_rep("mlb_pipeline", "2016-02-01", LONG + " A member of the '21 class.")],
            "c": [_rep("mlb_pipeline", "2016-02-01", LONG + " He broke out in 2015.")],
            "d": [_rep("mlb_pipeline", "2016-02-01", LONG + " ETA 2017.")]}
    out = {r["player_key"]: r for r in T.attach_text(rows, reps)}
    assert out["a"]["report_absent"] == 1.0 and out["a"]["report_in_window"] == 1.0
    assert out["a"]["report_dropped"][0]["later_years"] == [2021]
    assert out["b"]["report_absent"] == 1.0
    assert out["c"]["report_absent"] == 0.0 and out["c"]["report_dropped"] == []
    # a forward ETA is a later year too: dropped, as the residual rate counts it
    assert out["d"]["report_absent"] == 1.0
    assert T.later_years("in 2021", 2016) == [2021]
    assert T.later_years("in 2016 and '16", 2016) == []
    assert T.clean_report(LONG + " by 2019", 2018)["dropped"] is True


def test_carried_identical_text_is_counted():
    rows = [_row("a", 2016), _row("b", 2016)]
    reps = {"a": [_rep("mlb_pipeline", "2015-02-01", LONG), _rep("mlb_pipeline", "2016-02-01", LONG)],
            "b": [_rep("mlb_pipeline", "2015-02-01", LONG + " x"),
                  _rep("mlb_pipeline", "2016-02-01", LONG + " y")]}
    out = {r["player_key"]: r for r in T.attach_text(rows, reps)}
    assert out["a"]["report_carried"] == 1.0 and out["a"]["report_sources"][0]["carried"]
    assert out["b"]["report_carried"] == 0.0
    rec = T.coverage_receipt({"hit": {2016: list(out.values())}})["by_side_vintage"]["hit:2016"]
    assert rec == {"rows": 2, "with_report_in_window": 2, "reports_dropped_later_year": 0,
                   "rows_dropped_later_year": 0, "with_text": 2, "carried_identical": 1,
                   "vintage_dropped": False, "by_source": {"mlb_pipeline": 2},
                   "median_report_len": int(np.median([len(LONG), len(LONG) + 2]))}


def test_load_reports_reads_the_window_and_the_length_floor(tmp_path):
    db = tmp_path / "p.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY, source TEXT, snapshot_date "
                "TEXT, interval_label TEXT, player_key TEXT, player_name TEXT, tools_json TEXT)")
    def ins(src, d, pk, rep):
        con.execute("INSERT INTO snapshots (source, snapshot_date, interval_label, player_key, "
                    "player_name, tools_json) VALUES (?,?,?,?,?,?)",
                    (src, d, d, pk, pk, json.dumps({"fb": 60.0, "_extras": {"report": rep}})))
    ins("mlb_pipeline", "2016-02-01", "a", LONG)
    ins("mlb_pipeline", "2016-02-01", "b", "short note")
    ins("fangraphs", "2019-02-13", "a", LONG)
    ins("baseballamerica", "2016-02-01", "a", LONG)
    ins("mlb_pipeline", "2020-02-01", "a", LONG)
    con.commit()
    con.close()
    got = T.load_reports(db_path=db, lo="2015-01-01", hi="2019-05-01")
    assert sorted(got) == ["a"]
    assert [(r["source"], r["date"]) for r in got["a"]] == [("fangraphs", "2019-02-13"),
                                                          ("mlb_pipeline", "2016-02-01")]


# ---------------------------------------------------------------------------
# 3. grade strings and dates never reach the tokenizer
# ---------------------------------------------------------------------------

def test_grade_strings_fv_eta_and_years_are_stripped():
    raw = ("Scouting Grades* (present/future): Hit: 3/4 | Power: 4/5 | Run: 6/6 | Arm: 7/7 "
           "| Field: 4/5 | Overall: 4/5 " + LONG + " We have him as a 45/50 FV, a 40 FV "
           "floor, on the FV continuum. ETA 2019. ETA: 2018. Pitching grades: Fastball: 80 "
           "| Slider 65 | Overall: 70 The '18 draft and the 2011 season.")
    t = T.strip_grades_and_dates(raw)
    for bad in ("Overall", "Scouting", "FV", "ETA", "grades", "Fastball", "Slider", "Hit:",
                "2019", "2018", "2011", "'18", "/", "|"):
        assert bad not in t, (bad, t)
    assert "loose, quick swing" in t and "draft" in t and "season" in t
    # the tokenizer keeps letter tokens only
    vec = T.fit_vectorizer(["velocity 98 mph and 2019 up to 80 grade " + LONG] * 6, min_df=1)
    assert all(re.fullmatch(r"[a-z][a-z']+", tok) for tok in vec.vocabulary_)


# ---------------------------------------------------------------------------
# 4. the fold
# ---------------------------------------------------------------------------

def _corpus(seed=7):
    rng = np.random.default_rng(seed)
    words = ["swing", "arm", "glove", "fastball", "command", "projection", "frame",
             "approach", "power", "speed", "makeup", "bat", "control", "slider"]
    def doc(signal):
        n = int(rng.integers(30, 50))
        ws = list(rng.choice(words, n))
        if signal:
            ws += ["zephyr"] * 3
        rng.shuffle(ws)
        return " ".join(ws)
    train, target, event = [], [], []
    k = 0
    for V in (2013, 2014, 2015):
        for _ in range(120):
            sig = bool(rng.integers(0, 2))
            fv = float(rng.choice([42.5, 47.5, 52.5, 57.5]))
            train.append({"player_key": f"t{k}", "vintage": V, "fv": fv,
                          "report_text": doc(sig) if rng.random() > 0.1 else None})
            target.append(0.02 * fv + (1.0 if sig else 0.0) + rng.normal(0, 0.3))
            event.append(float((0.5 if sig else 0.1) > rng.random()))
            k += 1
    test = []
    for i in range(60):
        sig = i % 2 == 0
        test.append({"player_key": f"v{i}", "vintage": 2016,
                     "fv": float(rng.choice([42.5, 47.5, 52.5, 57.5])),
                     "report_text": doc(sig) if i % 10 else None})
    return train, target, event, test


def test_fold_learns_a_planted_word_and_leaves_absent_rows_none():
    train, target, event, test = _corpus()
    out = T.fold_columns("hit", 2016, train, test, target=target, event=event)
    assert out["offered"] == ["txt_skill_hit", "txt_time_hit"]
    assert out["train_vintages"] == [2013, 2014, 2015]
    for name in out["offered"]:
        assert out["fits"][name]["status"] == "ok"
        assert out["fits"][name]["vocab_size"] >= 10
        with_w = [out["columns"][r["player_key"]][name] for i, r in enumerate(test)
                  if i % 2 == 0 and i % 10]
        without = [out["columns"][r["player_key"]][name] for i, r in enumerate(test)
                   if i % 2 == 1 and i % 10]
        assert np.mean(with_w) > np.mean(without) + 0.05
    assert out["columns"]["v0"]["txt_skill_hit"] is None   # no text: None, never 0
    assert out["columns"]["v0"]["txt_time_hit"] is None
    # a withheld head is not offered
    only = T.fold_columns("pit", 2016, train, test, target=target, event=event,
                          offered=("time",))
    assert only["offered"] == ["txt_time_pit"]
    assert set(only["columns"]["v1"]) == {"txt_time_pit"}


def test_vocabulary_of_fold_v_holds_no_token_first_seen_at_v():
    train, target, event, test = _corpus()
    vec = T.fit_vectorizer([r["report_text"] for r in train if r["report_text"]])
    train_tokens = set()
    for r in train:
        if r["report_text"]:
            train_tokens |= set(re.findall(r"[a-z][a-z']+", r["report_text"].lower()))
    assert set(vec.vocabulary_) <= train_tokens
    base = T.fold_columns("hit", 2016, train, test, target=target, event=event)
    spiked = [dict(r, report_text=(r["report_text"] + " quokka quokka quokka")
                   if r["report_text"] else None) for r in test]
    again = T.fold_columns("hit", 2016, train, spiked, target=target, event=event)
    assert again["columns"] == base["columns"]
    assert "quokka" not in vec.vocabulary_


def test_fold_refuses_v_frame_players_and_later_vintages():
    train, target, event, test = _corpus()
    leak = train + [dict(test[1], vintage=2015)]
    with pytest.raises(ValueError, match="GATE s4.5"):
        T.fold_columns("hit", 2016, leak, test, target=target + [0.0], event=event + [0.0])
    late = train + [dict(train[0], player_key="late", vintage=2016)]
    with pytest.raises(ValueError, match="strictly below"):
        T.fold_columns("hit", 2016, late, test, target=target + [0.0], event=event + [0.0])
    with pytest.raises(ValueError, match="align"):
        T.fold_columns("hit", 2016, train, test, target=target[:-1], event=event)


@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_vintages_raise_everywhere(V):
    with pytest.raises(F.ReservedFrameError):
        T.attach_text([_row("a", V)], {})
    train, target, event, test = _corpus()
    with pytest.raises(F.ReservedFrameError):
        T.fold_columns("hit", V, train, [dict(r, vintage=V) for r in test],
                       target=target, event=event)
    with pytest.raises(F.ReservedFrameError):
        T.text_rows("hit", (2016, V), universe={}, reports={})


def test_within_pct_matches_efv_v2_model():
    import efv_v2_model as H
    rng = np.random.default_rng(3)
    vals = rng.choice([42.5, 47.5, 52.5, 57.5, 62.5], 200)
    groups = list(rng.choice([2013, 2014, 2015], 200))
    assert np.allclose(T.within_pct(vals, groups), H.within_pct(vals, groups))


def test_text_scalar_is_residual_to_consensus():
    """With the target a pure function of u_c the ridge sees no residual signal: the
    scalar's spread is tiny beside a planted signal's."""
    train, target, event, test = _corpus()
    u = T.within_pct([r["fv"] for r in train], [r["vintage"] for r in train])
    flat = T.fold_columns("hit", 2016, train, test, target=list(u), event=list(u > 0.5))
    live = T.fold_columns("hit", 2016, train, test, target=target, event=event)
    def spread(out, name):
        v = [x[name] for x in out["columns"].values() if x[name] is not None]
        return float(np.std(v))
    assert spread(flat, "txt_skill_hit") < 0.25 * spread(live, "txt_skill_hit")


# ---------------------------------------------------------------------------
# 5. which heads are offered
# ---------------------------------------------------------------------------

def test_offered_columns_read_the_ds03_verdict(tmp_path):
    p = tmp_path / "bal.json"
    assert T.offered_columns("hit", p) == ("time",)       # no probe yet: timing only
    p.write_text(json.dumps({"text": {"balance": {
        "hit": {"report_absent": {"verdict": "BALANCED"}},
        "pit": {"report_absent": {"verdict": "IMBALANCED"}}}}}), encoding="utf-8")
    assert T.offered_columns("hit", p) == ("skill", "time")
    assert T.offered_columns("pit", p) == ("time",)
    assert T.balance_verdict("pit", p) == "IMBALANCED"
    assert T.column_name("skill", "pit") == "txt_skill_pit"
    with pytest.raises(ValueError):
        T.column_name("war", "pit")


# ---------------------------------------------------------------------------
# 6. no FV-cell grouping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [SRC, TOOL])
def test_no_fv_cell_grouping(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _names(tree):
        low = name.lower()
        assert not any(t in low for t in _BANNED_TOKENS), (path.name, name)
    for node in ast.walk(tree):
        if path == SRC and isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            low = node.value.lower()
            assert not any(t in low for t in _BANNED_TOKENS), (path.name, node.value)


def test_no_em_dash_in_the_family():
    for p in (SRC, TOOL, Path(__file__)):
        txt = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt, p.name


# ---------------------------------------------------------------------------
# 7. the committed receipt
# ---------------------------------------------------------------------------

def test_merge_text_key_keeps_every_other_key_and_the_line_ending(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import efv_text_balance as TB
    p = tmp_path / "bal.json"
    base = {"generated_at": "x", "balance": {"hit": {"milb_absent": {"verdict": "BALANCED"}}},
            "probes": {"a": 1}, "n_probes": 1}
    p.write_bytes((json.dumps(base, indent=1) + "\n").replace("\n", "\r\n").encode())
    TB.merge_text_key(p, {"balance": {"hit": {"report_absent": {"verdict": "BALANCED"}}}})
    raw = p.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    doc = json.loads(raw)
    assert {k: doc[k] for k in base} == base
    assert doc["text"]["balance"]["hit"]["report_absent"]["verdict"] == "BALANCED"
    TB.merge_text_key(p, doc["text"])
    assert p.read_bytes() == raw
    assert TB.VINTAGES == tuple(v for v in F.DEV_VINTAGES if v >= T.FIRST_TEXT_VINTAGE)
    assert not set(TB.VINTAGES) & F.RESERVED_LV


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("data/efv_identity_balance.json not built")
    doc = json.loads(ART.read_text(encoding="utf-8"))
    if T.BALANCE_KEY not in doc:
        pytest.skip("the text key is not in data/efv_identity_balance.json")
    return doc


def test_receipt_text_key_is_for_this_builder(art):
    blk = art[T.BALANCE_KEY]
    sha = hashlib.sha256(SRC.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert blk["code"]["builder_sha256"] == sha, (
        "efv_text_features.py changed since the text key was built; rerun "
        "python tools/efv_text_balance.py")
    assert blk["role"] == "development"
    g = blk["guards"]
    assert not set(g["vintages_read"]) & set(F.RESERVED_LV)
    assert max(g["vintages_read"]) < min(F.RESERVED_LV)
    assert min(g["vintages_read"]) == T.FIRST_TEXT_VINTAGE
    assert g["reserved_vm_pins"] == []
    assert blk["settings"]["min_df"] == T.MIN_DF


def test_receipt_verdict_decides_the_offered_heads(art):
    blk = art[T.BALANCE_KEY]
    for side in F.SIDES:
        b = blk["balance"][side]["report_absent"]
        assert b["verdict"] in ("BALANCED", "IMBALANCED", "CONSTANT")
        if b["verdict"] != "CONSTANT":
            lo, hi = b["ci95"]
            assert (lo <= 0 <= hi) is (b["verdict"] == "BALANCED")
            assert b["B_used"] <= 500
        want = [T.column_name(h, side) for h in T.offered_columns(side)]
        assert blk["offered_columns"][side] == want
    # the rest of the receipt is the identity tool's, untouched
    assert "report_absent" not in art["balance"]["hit"]
    assert not any(k.startswith("DS-03:balance.report") for k in art["probes"])


def test_receipt_coverage_and_registration(art):
    blk = art[T.BALANCE_KEY]
    cov = blk["coverage"]["by_side_vintage"]
    for key, c in cov.items():
        side, V = key.split(":")
        assert side in F.SIDES and T.FIRST_TEXT_VINTAGE <= int(V) < min(F.RESERVED_LV)
        assert c["with_text"] <= c["with_report_in_window"] <= c["rows"]
        assert c["rows_dropped_later_year"] <= c["reports_dropped_later_year"]
        assert c["with_text"] + c["rows_dropped_later_year"] == c["with_report_in_window"]
        assert c["carried_identical"] <= c["with_text"]
        assert set(c["by_source"]) <= set(T.TEXT_SOURCES)
        if int(V) < T.TEXT_SOURCES["fangraphs"]:
            assert "fangraphs" not in c["by_source"]
    assert set(blk["coverage"]["no_row_sources"]) == {"baseballamerica", "espn",
                                                      "just_baseball", "tjstats"}
    reg = blk["registration"]["later_year_by_snapshot_year"]
    assert reg["2011"] == [128, 152] and reg["2012"] == [278, 453]
    assert reg["2013"] == [8, 696] and reg["2019"] == [27, 995]
    assert blk["registration"]["report_rows"] == 22127


@pytest.mark.skipif(not (ROOT / "prospects.db").exists(), reason="no prospects.db")
def test_real_frame_rows_carry_in_window_text_only(art):
    rows = T.text_rows("hit", (2016,))[2016]
    c = art[T.BALANCE_KEY]["coverage"]["by_side_vintage"]["hit:2016"]
    assert len(rows) == c["rows"]
    assert sum(1 for r in rows if not r["report_absent"]) == c["with_text"]
    for r in rows:
        lo, hi = r["window"]
        if r["report_absent"]:
            assert r["report_text"] is None and r["report_date"] is None
            continue
        assert lo <= r["report_date"] < hi
        assert all(lo <= s["date"] < hi for s in r["report_sources"])
        assert all(s["source"] in r["real_sources"] for s in r["report_sources"])
        assert not T.later_years(r["report_text"], 2016)
        assert not re.search(r"\bFV\b|\bETA\b|Overall:", r["report_text"])
