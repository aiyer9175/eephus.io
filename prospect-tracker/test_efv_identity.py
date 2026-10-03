"""DS-03 pins (bug B4, docs/efv-v2/DRIVER_SYSTEM_V2.md): the outcome-blind identity
resolver for list-vintage rows.

1. The resolver module reads no debut, major league, WAR or label column and does not
   use the record's stored id or birth date (an AST scan of efv_identity.py).
2. Behaviour: a row's resolution does not move when every outcome field on its record
   changes; candidates are limited to people in affiliated minor league ball before V;
   an ambiguous name stays unresolved unless the SIDE or the RECENCY tiebreak (pre-V
   minor league lines only) leaves exactly one candidate.
3. efv_vintage_frame keys every input on the resolver's id, never the record's.
4. The committed receipt (data/efv_identity_balance.json): the W3 > 0 share is reported
   for every missingness indicator on both sides, only BALANCED indicators are
   admissible to the timing head, and the I2 H1 fake gain (+0.03 under a resolver that
   reads the debut) appears under the counterfactual and vanishes under efv_identity.
   The receipt must be rebuilt whenever the resolver changes (sha pin).
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_identity as ID  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

ART = ROOT / "data" / "efv_identity_balance.json"

# ---------------------------------------------------------------------------
# 1. the source never reads an outcome
# ---------------------------------------------------------------------------

_FORBIDDEN = re.compile(
    r"debut|career|(^|_)war($|_)|mlb_first|reached|(^|_)label|(^|_)w3|(^|_)r3|"
    r"mlbam_id|birth|all_sports|player_index|sport1|first_mlb|outcome")
_ALLOWED_IMPORTS = {"__future__", "json", "re", "unicodedata", "dataclasses", "pathlib",
                    "milb_history"}


def _docstring_ids(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and \
                    isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _tokens(tree):
    docs = _docstring_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            yield node.value, node.lineno


def test_resolver_source_reads_no_outcome_column():
    tree = ast.parse((ROOT / "efv_identity.py").read_text(encoding="utf-8"))
    for tok, line in _tokens(tree):
        assert not _FORBIDDEN.search(tok.lower()), (tok, line)
        assert tok != "MLB", line


def test_resolver_imports_nothing_that_holds_an_outcome():
    tree = ast.parse((ROOT / "efv_identity.py").read_text(encoding="utf-8"))
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert imported <= _ALLOWED_IMPORTS, imported - _ALLOWED_IMPORTS


def test_index_reads_minor_league_sports_only():
    assert 1 not in ID.INDEX_SPORTS
    assert set(ID.INDEX_SPORTS) == set(ID.mh.MINOR_SPORTS)
    tree = ast.parse((ROOT / "efv_identity.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "season_splits"]
    assert calls, "the index no longer reads season_splits"
    for c in calls:
        assert isinstance(c.args[0], ast.Name) and c.args[0].id == "sport", ast.dump(c)
        assert any(k.arg == "fetch" and isinstance(k.value, ast.Constant)
                   and k.value.value is False for k in c.keywords), "index must not fetch"


# ---------------------------------------------------------------------------
# 2. behaviour
# ---------------------------------------------------------------------------

def _index():
    idx = ID.NameIndex()
    idx.add("Jose Perez", 101, 2014)        # in ball from 2014
    idx.add("Jose Perez", 102, 2017)        # a second Jose Perez from 2017
    idx.add("Luis Ortiz Jr.", 201, 2015)
    idx.add("Ana Ruiz", 301, 2018)          # drafted in June 2018
    return idx


def test_candidates_only_before_the_read():
    idx = _index()
    assert ID.resolve("Jose Perez", 2016, idx).person_id == 101     # 102 not yet in ball
    r = ID.resolve("Jose Perez", 2018, idx)
    assert r.person_id is None and r.how == ID.HOW_AMBIGUOUS and r.n_candidates == 2
    assert ID.resolve("Ana Ruiz", 2018, idx).how == ID.HOW_NONE    # June 2018 is after
    assert ID.resolve("Ana Ruiz", 2019, idx).person_id == 301
    assert ID.resolve("", 2019, idx).how == ID.HOW_NO_NAME


def test_name_normalization():
    idx = _index()
    assert ID.resolve("Luis Ortíz", 2016, idx).person_id == 201
    assert ID.norm_name("José Pérez III") == ID.norm_name("Jose Perez")


def test_resolution_is_invariant_to_every_outcome_field():
    idx = _index()
    base = {"player_key": "jose_perez", "player_name": "Jose Perez", "points": []}
    variants = [
        {},
        {"debut_date": "2019-06-01"}, {"debut_date": None},
        {"mlbam_id": 102}, {"mlbam_id": 999}, {"mlbam_id": None},
        {"birth_date": "1998-01-01"}, {"career_war": {"total": 12.0}},
        {"debuted_value": {"wag": {"regressed_wag": 1.0}}}, {"status": "debuted"},
        {"career_stats": {"mlb": [1]}},
    ]
    for V in (2016, 2018):
        got = {ID.resolve_record(dict(base, **v), V, idx) for v in variants}
        assert len(got) == 1, (V, got)


def test_frame_keys_inputs_on_the_resolved_id(monkeypatch):
    """The record carries id 999 (as a debuted record would); the frame must key the
    MiLB read on the name-resolved id and keep 999 for audit only."""
    idx = _index()
    seen = []

    def fake_milb(mlbam, V, birth, side, cutoff=None, **kw):
        seen.append(mlbam)
        return None
    monkeypatch.setattr(D, "_milb_features", fake_milb)
    rec = {"player_key": "jose_perez", "player_name": "Jose Perez", "mlbam_id": 999,
           "position": "SS", "birth_date": "1998-01-01",
           "points": [{"snapshot_date": "2016-02-01", "consensus_fv_raw": 45.0,
                       "per_source": {"mlb_pipeline": {"fv_published": 45,
                                                       "snapshot_date": "2016-02-01"}}}]}
    monkeypatch.setattr(F, "_mlb_ids", lambda season: frozenset())
    row = F.frame_row(rec, "hit", 2016, excl=frozenset(), index=idx)
    assert row is not None
    assert row["mlbam_id"] == 101 and row["id_how"] == ID.HOW_RESOLVED
    assert row["record_mlbam_id"] == 999
    assert seen == [101]
    # an ambiguous name leaves the row without an id, whatever the record carries
    seen.clear()
    rec18 = copy.deepcopy(rec)
    for p in rec18["points"]:
        p["snapshot_date"] = "2018-02-01"
        p["per_source"]["mlb_pipeline"]["snapshot_date"] = "2018-02-01"
    row = F.frame_row(rec18, "hit", 2018, excl=frozenset(), index=idx)
    assert row["mlbam_id"] is None and row["id_how"] == ID.HOW_AMBIGUOUS
    assert seen == [None]


def _index_with_lines():
    """Names with several candidates whose pre-V minor league lines differ by group
    and by season, the evidence the two tiebreaks read."""
    idx = ID.NameIndex()
    # Jose Perez: 101 a hitter (hitting lines, one blowout inning pitched), 102 a
    # pitcher (pitching lines plus a 0-PA batting line, as pitchers carry)
    for s in (2014, 2015, 2016):
        idx.add("Jose Perez", 101, s, "hitting", 420)
    idx.add("Jose Perez", 101, 2016, "pitching", 3)
    for s in (2015, 2016):
        idx.add("Jose Perez", 102, s, "pitching", 310)
        idx.add("Jose Perez", 102, s, "hitting", 0)
    # Juan Cruz: two hitters; 201 played 2012 and 2013, 202 played 2013, 2016 and 2017
    for s in (2012, 2013):
        idx.add("Juan Cruz", 201, s, "hitting", 300)
    for s in (2013, 2016, 2017):
        idx.add("Juan Cruz", 202, s, "hitting", 300)
    # Luis Mora: two pitchers with recent lines (no tiebreak can split them)
    for pid in (301, 302):
        for s in (2016, 2017):
            idx.add("Luis Mora", pid, s, "pitching", 200)
    # Pedro Gil: 401 a hitter with lines, 402 a June 2017 draft selection with no line
    for s in (2015, 2016, 2017):
        idx.add("Pedro Gil", 401, s, "hitting", 350)
    idx.add("Pedro Gil", 402, 2017)
    # Raul Soto: a pitcher (501) and a draft selection with no line (502); a hitter row
    for s in (2016, 2017):
        idx.add("Raul Soto", 501, s, "pitching", 250)
    idx.add("Raul Soto", 502, 2017)
    return idx


def test_side_tiebreak_keeps_the_candidate_of_the_rows_own_group():
    idx = _index_with_lines()
    hit = ID.resolve("Jose Perez", 2018, idx, "hit")
    assert (hit.person_id, hit.how, hit.n_candidates) == (101, ID.HOW_SIDE, 2)
    pit = ID.resolve("Jose Perez", 2018, idx, "pit")
    assert (pit.person_id, pit.how, pit.n_candidates) == (102, ID.HOW_SIDE, 2)
    # a candidate's group is where his exposure is, not where any line is: the
    # pitcher's 0-PA batting line and the hitter's blowout inning do not count
    assert ID._group_of(idx.lines("Jose Perez", 102, 2018)) == "pitching"
    assert ID._group_of(idx.lines("Jose Perez", 101, 2018)) == "hitting"
    # the draft selection has no line, so no group: the hitter with lines is kept
    assert ID.resolve("Pedro Gil", 2018, idx, "hit").person_id == 401
    assert ID.resolve("Pedro Gil", 2018, idx, "hit").how == ID.HOW_SIDE
    # a hitter row whose candidates are a pitcher and a lineless draftee: nobody is
    # in the row's group, so the row stays ambiguous (recency never sees the pitcher)
    r = ID.resolve("Raul Soto", 2018, idx, "hit")
    assert r.person_id is None and r.how == ID.HOW_AMBIGUOUS and r.n_candidates == 2
    assert ID.resolve("Raul Soto", 2018, idx, "pit").person_id == 501


def test_recency_tiebreak_keeps_the_candidate_with_a_line_in_v1_or_v2():
    idx = _index_with_lines()
    # V 2018: both are hitters; only 202 has a line in 2016 or 2017
    r = ID.resolve("Juan Cruz", 2018, idx, "hit")
    assert (r.person_id, r.how, r.n_candidates) == (202, ID.HOW_RECENCY, 2)
    # V 2015: both have a 2013 line (V - 2), so recency leaves two: ambiguous
    r = ID.resolve("Juan Cruz", 2015, idx, "hit")
    assert r.person_id is None and r.how == ID.HOW_AMBIGUOUS and r.n_candidates == 2
    # V 2013: only 201 was in ball before the read: the plain unique rule
    assert ID.resolve("Juan Cruz", 2013, idx, "hit").how == ID.HOW_RESOLVED
    # lines before V only: at V 2017 the 2017 line is not yet readable, 2016 is
    assert ID.resolve("Juan Cruz", 2017, idx, "hit").person_id == 202
    assert idx.lines("Juan Cruz", 202, 2017) == {"hitting": {2013: 300.0, 2016: 300.0}}


def test_no_change_when_the_tiebreaks_cannot_split_or_no_side_is_given():
    idx = _index_with_lines()
    # two pitchers with recent lines: ambiguous on both sides
    for side in ("hit", "pit"):
        r = ID.resolve("Luis Mora", 2018, idx, side)
        assert r.person_id is None and r.how == ID.HOW_AMBIGUOUS and r.n_candidates == 2
    # without a side the tiebreaks do not run (the pre-tiebreak behaviour)
    for name in ("Jose Perez", "Juan Cruz", "Pedro Gil"):
        r = ID.resolve(name, 2018, idx)
        assert r.person_id is None and r.how == ID.HOW_AMBIGUOUS
    # an index without lines (the older fixture) resolves exactly as before
    idx0 = _index()
    assert ID.resolve("Jose Perez", 2018, idx0, "hit").how == ID.HOW_AMBIGUOUS
    assert ID.resolve("Jose Perez", 2016, idx0, "hit").person_id == 101
    assert ID.resolve("Ana Ruiz", 2019, idx0, "pit").person_id == 301
    assert set(ID.HOW_WITH_ID) == {ID.HOW_RESOLVED, ID.HOW_SIDE, ID.HOW_RECENCY}


def test_tiebreak_resolution_is_invariant_to_every_outcome_field():
    idx = _index_with_lines()
    variants = [
        {},
        {"debut_date": "2019-06-01"}, {"debut_date": None},
        {"mlbam_id": 102}, {"mlbam_id": 999}, {"mlbam_id": None},
        {"birth_date": "1998-01-01"}, {"career_war": {"total": 12.0}},
        {"debuted_value": {"wag": {"regressed_wag": 1.0}}}, {"status": "debuted"},
        {"career_stats": {"mlb": [1]}},
    ]
    for name, side, want in (("Jose Perez", "hit", 101), ("Jose Perez", "pit", 102),
                             ("Juan Cruz", "hit", 202), ("Luis Mora", "pit", None)):
        base = {"player_key": ID.norm_name(name), "player_name": name, "points": []}
        got = {ID.resolve_record(dict(base, **v), 2018, idx, side) for v in variants}
        assert len(got) == 1 and next(iter(got)).person_id == want, (name, got)


def test_frame_passes_its_routing_to_the_tiebreaks(monkeypatch):
    """The same printed name on the hitter frame and on the pitcher frame resolves to
    the candidate of each frame's own group, keyed on that id."""
    idx = _index_with_lines()
    seen = []

    def fake_milb(mlbam, V, birth, side, cutoff=None, **kw):
        seen.append((side, mlbam))
        return None
    monkeypatch.setattr(D, "_milb_features", fake_milb)
    monkeypatch.setattr(F, "_mlb_ids", lambda season: frozenset())
    pts = [{"snapshot_date": "2018-02-01", "consensus_fv_raw": 45.0,
            "per_source": {"mlb_pipeline": {"fv_published": 45,
                                            "snapshot_date": "2018-02-01"}}}]
    hitter = {"player_key": "jose_perez", "player_name": "Jose Perez", "mlbam_id": 999,
              "position": "SS", "birth_date": "1998-01-01", "points": copy.deepcopy(pts)}
    pitcher = {"player_key": "jose_perez_2", "player_name": "Jose Perez", "mlbam_id": 998,
               "position": "RHP", "birth_date": "1997-01-01", "points": copy.deepcopy(pts)}
    row = F.frame_row(hitter, "hit", 2018, excl=frozenset(), index=idx)
    assert row["mlbam_id"] == 101 and row["id_how"] == ID.HOW_SIDE
    assert row["id_candidates"] == 2 and row["record_mlbam_id"] == 999
    row = F.frame_row(pitcher, "pit", 2018, excl=frozenset(), index=idx)
    assert row["mlbam_id"] == 102 and row["id_how"] == ID.HOW_SIDE
    assert seen == [("hit", 101), ("pit", 102)]
    # the routing is the frame's: a pitcher record is not on the hitter frame at all
    assert F.frame_row(pitcher, "hit", 2018, excl=frozenset(), index=idx) is None


def test_lv_model_row_marks_unresolved_rows_unavailable():
    row = {"player_key": "x", "vintage": 2018, "window": ["2018-01-01", "2018-05-01"],
           "mlbam_id": None, "milb": None, "prior": {}}
    assert H.lv_model_row(row)["milb_unavailable"] is True


# ---------------------------------------------------------------------------
# 4. the committed receipt
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("data/efv_identity_balance.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_receipt_is_for_this_resolver(art):
    sha = hashlib.sha256((ROOT / "efv_identity.py").read_bytes()
                         .replace(b"\r\n", b"\n")).hexdigest()
    assert art["resolver"]["sha256"] == sha, (
        "efv_identity.py changed since data/efv_identity_balance.json was built; "
        "rerun python tools/efv_identity_balance.py")


def test_receipt_reads_no_reserved_frame(art):
    g = art["guards"]
    assert not set(g["vintages_read"]) & set(F.RESERVED_LV)
    assert max(g["vintages_read"]) < min(F.RESERVED_LV)
    assert g["reserved_vm_pins"] == []
    assert art["role"] == "development"


def test_w3_share_reported_for_every_indicator(art):
    sys.path.insert(0, str(ROOT / "tools"))
    import efv_identity_balance as TB
    names = [n for n, _ in TB.INDICATORS]
    for side in F.SIDES:
        for n in names:
            blk = art["balance"][side][n]
            assert blk["verdict"] in ("BALANCED", "IMBALANCED", "CONSTANT")
            if blk["verdict"] != "CONSTANT":
                assert 0.0 <= blk["w3_pos_share_with"] <= 1.0
                assert 0.0 <= blk["w3_pos_share_without"] <= 1.0
                lo, hi = blk["ci95"]
                assert (lo <= 0 <= hi) is (blk["verdict"] == "BALANCED")


def test_only_balanced_indicators_are_admissible(art):
    for side in F.SIDES:
        want = sorted(k for k, v in art["balance"][side].items()
                      if v["verdict"] == "BALANCED")
        assert art["timing_head_admissible"][side] == want
    # the leak B4 names is visible in the receipt: the counterfactual's missing-level
    # indicator and the record's own id are imbalanced on both sides
    for side in F.SIDES:
        assert art["balance"][side]["leaky_level_missing"]["verdict"] == "IMBALANCED"
        assert art["balance"][side]["record_id_missing"]["verdict"] == "IMBALANCED"


def test_i2_h1_fake_gain_appears_leaky_and_vanishes_blind(art):
    h1 = art["h1_regression"]
    leaky, blind = h1["leaky_reference"], h1["outcome_blind"]
    assert leaky["n"] == blind["n"] and leaky["rho_consensus"] == blind["rho_consensus"]
    # the counterfactual reproduces the fake win (I2: +0.0304, CI95 +0.0125 to +0.0496)
    assert leaky["delta_vs_consensus"] >= 0.015 and leaky["ci95"][0] > 0
    # the outcome-blind resolver removes it
    assert blind["ci95"][0] <= 0 <= blind["ci95"][1]
    assert abs(blind["delta_vs_consensus"]) < 0.015
    assert leaky["delta_vs_consensus"] - blind["delta_vs_consensus"] >= 0.015
    assert art["h1_regression_holds"] is True


def test_receipt_groups_nothing_by_grade(art):
    txt = json.dumps(art).lower()
    for tok in ("tier", "bucket", "fv_band", "fv_bin", "by_fv", "stratum"):
        assert tok not in txt, tok
    assert "—" not in txt and "–" not in txt
