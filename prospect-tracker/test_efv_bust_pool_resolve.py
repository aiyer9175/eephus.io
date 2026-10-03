"""EFV3 lane A G7 pins (tools/efv_bust_pool_resolve.py, owner answer lane A E3-Q4 = A):
the outcome-blind ids for the bust pool, dev-only behind a flag with the symmetry receipt.

1. The resolver path (RESOLVER_PATH, an AST scan of exactly those functions) reads no
   debut or major league column, no WAR, no stored id and no birth date, and calls the
   name index through efv_identity only.
2. A row's id does not move when its outcome fields change (synthetic index).
3. efv_dataset.BUST_POOL_IDS defaults off, and with it off the matrix builder opens no
   file and attaches no id (fixture half of the byte-identical pin; the real-data half is
   the two temp builds the commit records: hit 9628befb, pit 8864a3aa, before and after).
4. The committed id file and receipt: the symmetry clause, the probe, no reserved
   frame, nothing grouped by grade, no em-dash.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_dataset as D  # noqa: E402
import efv_identity as ID  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_bust_pool_resolve as BP  # noqa: E402

TOOL = ROOT / "tools" / "efv_bust_pool_resolve.py"
IDS = ROOT / "data" / "efv_bust_pool_ids.json"
RECEIPT = ROOT / "data" / "efv_bust_pool_receipt.json"

# ---------------------------------------------------------------------------
# 1. the resolver path never reads an outcome
# ---------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"debut|career|(^|_)war($|_)|mlb_first|reached|(^|_)label|(^|_)w3|(^|_)r3|"
    r"mlbam_id|birth|all_sports|player_index|sport1|first_mlb|outcome|search")
#: Names a resolver function may call outside the module's own path.
_ALLOWED_CALLS = {"resolve", "build_index", "_side_match", "get", "append", "max",
                  "int", "str", "isdigit", "dict"}


def _functions(tree) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _tokens(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            yield n.id, n.lineno
        elif isinstance(n, ast.Attribute):
            yield n.attr, n.lineno
        elif isinstance(n, ast.arg):
            yield n.arg, n.lineno
        elif isinstance(n, ast.keyword) and n.arg:
            yield n.arg, n.lineno
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value, n.lineno


def test_resolver_path_names_every_function_it_runs():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    fns = _functions(tree)
    assert set(BP.RESOLVER_PATH) <= set(fns)
    # resolve_pool and resolve_row reach nothing outside the path but efv_identity
    # and the frame's own side routing
    for name in BP.RESOLVER_PATH:
        fn = fns[name]
        body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                               and isinstance(fn.body[0].value, ast.Constant)) else fn.body
        for n in body:
            for c in ast.walk(n):
                if isinstance(c, ast.Call):
                    f = c.func
                    called = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                    assert called in _ALLOWED_CALLS or called in BP.RESOLVER_PATH, \
                        (name, called, c.lineno)


def test_resolver_path_reads_no_outcome_column():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    fns = _functions(tree)
    for name in BP.RESOLVER_PATH:
        fn = fns[name]
        body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                               and isinstance(fn.body[0].value, ast.Constant)) else fn.body
        for n in body:
            for tok, line in _tokens(n):
                assert not _FORBIDDEN.search(tok.lower()), (name, tok, line)
                assert tok != "MLB", (name, line)


def test_resolver_is_efv_identitys_and_the_index_is_minor_league_only():
    assert BP.resolve_row.__module__ == "efv_bust_pool_resolve"
    src = inspect.getsource(BP.resolve_row)
    assert "ID.resolve(" in src
    assert 1 not in ID.INDEX_SPORTS
    # no network path exists in the tool at all: no StatsAPI host, no HTTP client
    text = TOOL.read_text(encoding="utf-8").lower()
    assert "statsapi" not in text and "http" not in text
    assert "urllib" not in text and "requests" not in text and "import socket" not in text


# ---------------------------------------------------------------------------
# 2. behaviour on a synthetic index
# ---------------------------------------------------------------------------

def _index():
    idx = ID.NameIndex()
    for s in (2014, 2015, 2016):
        idx.add("Jose Perez", 101, s, "hitting", 420)
    for s in (2015, 2016):
        idx.add("Jose Perez", 102, s, "pitching", 310)
    idx.add("Ana Ruiz", 301, 2018)             # June 2018 draft selection, no line
    for s in (2016, 2017):
        idx.add("Luis Mora", 401, s, "pitching", 200)
        idx.add("Luis Mora", 402, s, "pitching", 200)
    return idx


def _rec(name, last_year, position="SS", **extra):
    pts = [] if last_year is None else [
        {"snapshot_date": f"{last_year}-02-01", "consensus_fv_raw": 40.0}]
    return dict({"player_key": ID.norm_name(name), "player_name": name,
                 "position": position, "points": pts}, **extra)


def test_read_year_is_the_season_after_the_last_list_year():
    idx = _index()
    # listed in 2018 only, drafted in June 2018: the read at 2019 sees the pick
    r = BP.resolve_row(_rec("Ana Ruiz", 2018), idx)
    assert (r["last_list_year"], r["read_year"], r["person_id"], r["how"]) == \
        (2018, 2019, 301, ID.HOW_RESOLVED)
    # no list point: no read year, unresolved, named
    r = BP.resolve_row(_rec("Ana Ruiz", None), idx)
    assert r["person_id"] is None and r["how"] == BP.HOW_NO_LIST_YEAR
    assert r["read_year"] is None and r["last_list_year"] is None
    assert BP.read_year(None) is None and BP.read_year(2020) == 2021


def test_side_routes_the_tiebreak_and_unknown_side_runs_none():
    idx = _index()
    hit = BP.resolve_row(_rec("Jose Perez", 2017, "SS"), idx)
    pit = BP.resolve_row(_rec("Jose Perez", 2017, "RHP"), idx)
    assert (hit["person_id"], hit["how"], hit["side"]) == (101, ID.HOW_SIDE, "hit")
    assert (pit["person_id"], pit["how"], pit["side"]) == (102, ID.HOW_SIDE, "pit")
    none = BP.resolve_row(_rec("Jose Perez", 2017, None), idx)
    assert none["side"] is None and none["person_id"] is None
    assert none["how"] == ID.HOW_AMBIGUOUS
    # two pitchers with recent lines stay ambiguous whatever the side
    r = BP.resolve_row(_rec("Luis Mora", 2018, "RHP"), idx)
    assert r["person_id"] is None and r["how"] == ID.HOW_AMBIGUOUS


def test_id_does_not_move_when_outcome_fields_change():
    idx = _index()
    variants = [
        {},
        {"debut_date": "2019-06-01"}, {"debut_date": None},
        {"mlbam_id": 102}, {"mlbam_id": 999}, {"mlbam_id": None},
        {"birth_date": "1998-01-01"}, {"career_war": {"total": 12.0}},
        {"debuted_value": {"wag": {"regressed_wag": 1.0}}}, {"status": "debuted"},
        {"career_stats": {"mlb": [1]}}, {"current_level": "MLB"},
    ]
    for name, pos, want in (("Jose Perez", "SS", 101), ("Jose Perez", "RHP", 102),
                            ("Ana Ruiz", "SS", 301), ("Luis Mora", "RHP", None)):
        got = {(r["person_id"], r["how"]) for r in
               (BP.resolve_row(_rec(name, 2018, pos, **v), idx) for v in variants)}
        assert len(got) == 1 and next(iter(got))[0] == want, (name, got)


def test_resolve_pool_keeps_order_and_reads_every_record():
    idx = _index()
    recs = [_rec("Ana Ruiz", 2018), _rec("Jose Perez", 2017, "SS"), _rec("Nobody", 2017)]
    out = BP.resolve_pool(recs, idx)
    assert [r["player_key"] for r in out] == [r["player_key"] for r in recs]
    assert [r["person_id"] for r in out] == [301, 101, None]
    assert out[2]["how"] == ID.HOW_NONE


# ---------------------------------------------------------------------------
# 3. the flag: off by default, and off means untouched
# ---------------------------------------------------------------------------

def test_flag_defaults_off():
    assert D.BUST_POOL_IDS is False
    assert D.BUST_POOL_IDS_FILE == "efv_bust_pool_ids.json"


def test_flag_off_attaches_nothing_and_opens_nothing(monkeypatch):
    monkeypatch.setattr(D, "BUST_POOL_IDS", False)

    def _boom(path=None):
        raise AssertionError("bust_pool_ids() called with the flag off")
    monkeypatch.setattr(D, "bust_pool_ids", _boom)
    rec = {"player_key": "a_b", "player_name": "A B", "mlbam_id": None, "points": []}
    acct = {"bust_seen": 1}
    before = copy.deepcopy(acct)
    out = D._with_bust_pool_id(rec, {"a_b": 555}, acct)
    assert out is rec and out.get("mlbam_id") is None and acct == before
    # the builder opens the file behind the flag and nowhere else
    src = inspect.getsource(D.build_matrix)
    assert "bust_pool_ids() if BUST_POOL_IDS else {}" in src
    assert src.count("bust_pool_ids(") == 1
    assert src.index("rec = _with_bust_pool_id(") < src.index("F1 bust-loop guard")


def test_flag_on_attaches_only_to_rows_without_a_stored_id(monkeypatch):
    monkeypatch.setattr(D, "BUST_POOL_IDS", True)
    pool = {"a_b": 555, "c_d": 777}
    acct = {}
    no_id = {"player_key": "a_b", "mlbam_id": None}
    with_id = {"player_key": "c_d", "mlbam_id": 123}
    not_in_pool = {"player_key": "e_f", "mlbam_id": None}
    out = D._with_bust_pool_id(no_id, pool, acct)
    assert out is not no_id and out["mlbam_id"] == 555 and no_id["mlbam_id"] is None
    assert D._with_bust_pool_id(with_id, pool, acct) is with_id
    assert D._with_bust_pool_id(not_in_pool, pool, acct) is not_in_pool
    assert acct == {"bust_pool_id_applied": 1}


def test_loader_refuses_a_blocked_file_and_reads_rows_otherwise(tmp_path):
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"symmetry": {"blocked": False},
                              "rows": [{"player_key": "a_b", "person_id": 555},
                                       {"player_key": "c_d", "person_id": None},
                                       {"player_key": "e_f", "person_id": "x"}]}),
                  encoding="utf-8")
    assert D.bust_pool_ids(ok) == {"a_b": 555}
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"symmetry": {"blocked": True, "verdict": "SYMMETRY_BLOCKED"},
                                   "rows": [{"player_key": "a_b", "person_id": 555}]}),
                       encoding="utf-8")
    with pytest.raises(D.BustPoolIdsBlocked):
        D.bust_pool_ids(blocked)
    assert D.bust_pool_ids(tmp_path / "absent.json") == {}


def test_symmetry_clause_blocks_above_ten_points():
    def cov(h, p):
        return {"hit": {"share": h}, "pit": {"share": p}}
    ok = BP.symmetry(cov(90.0, 90.0), cov(81.0, 99.0))
    assert ok["blocked"] is False and ok["verdict"] == "SYMMETRY_OK"
    assert ok["by_side"]["hit"]["gap_points"] == 9.0
    bad = BP.symmetry(cov(90.0, 90.0), cov(79.9, 90.0))
    assert bad["blocked"] is True and bad["verdict"] == "SYMMETRY_BLOCKED"
    assert bad["by_side"]["hit"]["over_limit"] and not bad["by_side"]["pit"]["over_limit"]
    assert BP.SYMMETRY_MAX_GAP_POINTS == 10.0


# ---------------------------------------------------------------------------
# 4. the committed files
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ids():
    if not IDS.exists():
        pytest.skip("data/efv_bust_pool_ids.json not built")
    return json.loads(IDS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def receipt():
    if not RECEIPT.exists():
        pytest.skip("data/efv_bust_pool_receipt.json not built")
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_id_file_rows_are_the_no_id_pool_and_carry_the_fields(ids):
    assert ids["schema"] == BP.SCHEMA and ids["role"] == "development"
    assert ids["flag"] == {"module": "efv_dataset", "name": "BUST_POOL_IDS",
                           "default": False,
                           "reads_blocked": "the builder refuses this file while "
                                            "symmetry.blocked"}
    rows = ids["rows"]
    assert len(rows) == ids["pool"]["no_stored_id"] > 0
    keys = {"player_key", "person_id", "how", "n_candidates", "last_list_year",
            "read_year", "side", "bust2_before", "bust2_after"}
    for r in rows:
        assert keys <= set(r), r
        assert (r["person_id"] is not None) == (r["how"] in ID.HOW_WITH_ID), r
        if r["read_year"] is not None:
            assert r["read_year"] == r["last_list_year"] + 1
    assert sum(1 for r in rows if r["person_id"] is not None) == ids["pool"]["resolved"]
    assert ids["symmetry"]["blocked"] is False
    assert ids["symmetry"]["max_gap_points"] == BP.SYMMETRY_MAX_GAP_POINTS


def test_receipt_reports_the_clause_the_classes_and_the_probe(ids, receipt):
    assert receipt["generated_at"] == ids["generated_at"]
    assert receipt["symmetry"] == ids["symmetry"]
    for side in ("hit", "pit"):
        blk = receipt["symmetry"]["by_side"][side]
        assert blk["over_limit"] is (abs(blk["gap_points"]) > BP.SYMMETRY_MAX_GAP_POINTS)
        assert blk["debuted_share"] == receipt["coverage"]["debuted_rows"][side]["share"]
        assert blk["bust_share"] == receipt["coverage"]["bust_rows"][side]["share"]
    b2 = receipt["bust2"]
    assert b2["rows"] == ids["pool"]["no_stored_id"]
    assert sum(b2["by_before_after"].values()) == b2["rows"]
    for k, by_year in b2["by_before_after_and_last_list_year"].items():
        assert sum(by_year.values()) == b2["by_before_after"][k]
    assert set(b2["before"]) | set(b2["after"]) <= {"never", "censored_never", "reached"}
    probe = receipt["probes"][BP.PROBE_TAG]
    assert probe["verdict"] in ("BALANCED", "IMBALANCED", "CONSTANT")
    assert receipt["balance"]["verdict"] == probe["verdict"]
    assert receipt["n_probes"] == len(receipt["probes"]) == 1
    assert receipt["retired_asset"]["joins_null_id_pool"] == 0
    assert receipt["label_epoch"]["provider"] and receipt["label_epoch"]["resolved_through"]


def test_receipt_reads_no_reserved_frame_and_groups_nothing_by_grade(receipt):
    g = receipt["balance"]["guards"]
    assert not set(g["vintages_read"]) & set(F.RESERVED_LV)
    assert max(g["vintages_read"]) < min(F.RESERVED_LV)
    assert g["reserved_vm_pins"] == []
    txt = json.dumps(receipt).lower()
    for tok in ("tier", "bucket", "fv_band", "fv_bin", "by_fv", "stratum", "auc", "spearman"):
        assert tok not in txt, tok
    em_dash, en_dash = chr(0x2014), chr(0x2013)
    for path in (TOOL, IDS, RECEIPT, Path(__file__)):
        t = path.read_text(encoding="utf-8")
        assert em_dash not in t and en_dash not in t, path
