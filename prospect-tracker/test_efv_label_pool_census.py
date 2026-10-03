"""EFV3_A1 (EFV3_PLAN.md s3, LANE_A.md s1, s2 and s4): the label pool census is counts
only.

1. No key or stratum of data/efv_label_pool_census.json names an FV cell; the strata
   are the whitelist (source, list_year, vintage, side, debut_cohort, id_how,
   bust_class, label_view).
2. The development-frame counts reconcile to data/efv_identity_balance.json's rows
   block (frame_rows, by_how) within 40 rows per route, the 2026-09-30 identity
   split's own tolerance.
3. The reserved guard, called with no sha, raises for list vintages 2020 and 2021,
   the census never builds them, and their counts are copied from PROGRAM.md s2.4.
4. The artifact carries no spearman, auc or delta key; the tool computes no rater
   score and groups nothing by grade.
5. The ledger row (data/efv_progress.json, model_id efv_label_pool) is a development
   row with raters {} and deltas {}, resolvable None, note 'label pool census, no
   score', appended once.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_progress as P  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import war_source  # noqa: E402

TOOL = ROOT / "tools" / "efv_label_pool_census.py"
ART = ROOT / "data" / "efv_label_pool_census.json"
BAL = ROOT / "data" / "efv_identity_balance.json"
PROG = ROOT / "data" / "efv_progress.json"
PROGRAM_DOC = ROOT / "docs" / "efv-v2" / "PROGRAM.md"

WHITELIST = ("source", "list_year", "vintage", "side", "debut_cohort", "id_how",
             "bust_class", "label_view")
TOLERANCE_ROWS = 40          # the 2026-09-30 identity split's own tolerance
_FV_CELL = re.compile(
    r"(?:^|[^0-9])(?:35|40|45|50|55|60|65|70)(?:\+|plus)?(?:$|[^0-9])|tier|fv_cell|fv_bucket",
    re.I)
_SCORE_KEY = re.compile(r"spearman|auc|delta|rho|ci95", re.I)


def _tool():
    spec = importlib.util.spec_from_file_location("efv_label_pool_census", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def C():
    return _tool()


@pytest.fixture(scope="module")
def doc():
    if not ART.exists():
        pytest.skip("data/efv_label_pool_census.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def _walk_keys(o, out: list) -> list:
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k))
            _walk_keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_keys(v, out)
    return out


def _by_lists(o, out: list) -> list:
    if isinstance(o, dict):
        if isinstance(o.get("by"), list):
            out.append(list(o["by"]))
        for v in o.values():
            _by_lists(v, out)
    elif isinstance(o, list):
        for v in o:
            _by_lists(v, out)
    return out


# ---------------------------------------------------------------------------
# 1. no FV cell anywhere

def test_no_key_or_stratum_names_an_fv_cell(doc):
    bad = sorted({k for k in _walk_keys(doc, []) if _FV_CELL.search(k)})
    assert not bad, f"keys naming an FV cell or tier: {bad}"
    assert tuple(doc["strata"]) == WHITELIST
    for by in _by_lists(doc, []):
        assert set(by) <= set(WHITELIST), by
    assert doc["guards"]["no_rater_score"] is True


def test_no_emdash(doc):
    txt = json.dumps(doc, ensure_ascii=False)
    assert "—" not in txt and "–" not in txt


# ---------------------------------------------------------------------------
# 2. reconciliation to the identity balance receipt

def test_counts_reconcile_to_the_identity_balance_receipt(doc):
    if not BAL.exists():
        pytest.skip("data/efv_identity_balance.json not built")
    bal = json.loads(BAL.read_text(encoding="utf-8"))["rows"]
    tot = doc["frame"]["dev_totals"]
    assert tot["vintages"] == list(F.DEV_VINTAGES)
    assert abs(tot["rows"] - bal["frame_rows"]) <= TOLERANCE_ROWS, (tot, bal)
    for route in ("name_unique", "ambiguous", "no_candidate"):
        assert abs(tot["id_how"][route] - bal["by_how"][route]) <= TOLERANCE_ROWS, route
    assert tot["rows"] == sum(tot["by_side"].values())
    assert tot["rows"] == sum(tot["id_how"].values())
    built = [r for r in doc["frame"]["rows"] if r["built"]]
    assert sum(r["rows"] for r in built if r["vintage"] in F.DEV_VINTAGES) == tot["rows"]


# ---------------------------------------------------------------------------
# 3. the reserved guard

@pytest.mark.parametrize("v", sorted(F.RESERVED_LV))
def test_reserved_guard_raises_without_a_sha(v):
    assert v in (2020, 2021)
    with pytest.raises(F.ReservedFrameError):
        F.guard_score_request(v)
    with pytest.raises(F.ReservedFrameError):
        F.build_frame("hit", v, milb=False, sidecars=False, universe={})


def test_the_census_never_builds_a_reserved_vintage(C, doc):
    assert C.check_reserved_guard() == {"2020": "ReservedFrameError",
                                        "2021": "ReservedFrameError"}
    assert not (set(C.VINTAGES_BUILT) & set(F.RESERVED_LV))
    with pytest.raises(F.ReservedFrameError):
        C.frame_census(universe={}, vintages=(2020,), program_text="")
    assert doc["guards"]["reserved_lv"] == [2020, 2021]
    assert doc["guards"]["reserved_lv_guard_called_without_sha"] == {
        "2020": "ReservedFrameError", "2021": "ReservedFrameError"}
    assert not (set(doc["guards"]["vintages_built"]) & set(F.RESERVED_LV))
    for r in doc["frame"]["rows"]:
        if r["vintage"] in F.RESERVED_LV:
            assert r["built"] is False and r["id_how"] is None
            assert r["copied_from"] == {"path": "docs/efv-v2/PROGRAM.md", "section": "s2.4"}
        else:
            assert r["built"] is True


def test_reserved_counts_are_copied_from_program_md(C, doc):
    text = PROGRAM_DOC.read_text(encoding="utf-8")
    rlv = C._program_rlv_counts(text)
    rows = {(r["vintage"], r["side"]): r["rows"] for r in doc["frame"]["rows"]}
    for v in ("2020", "2021"):
        for side in F.SIDES:
            assert rows[(int(v), side)] == rlv[v][side]
    cp = doc["frame"]["reserved_copied"]
    assert cp["quote"] == rlv["quote"]
    # the stamp depends on the checkout's line endings (a CRLF worktree vs an LF tree).
    # It names the version the census copied: the file now, or the file at the census's
    # recorded commit when a later amendment (EFV3_A6, s2.5) edited PROGRAM.md outside
    # s2.4; the quote check above proves s2.4 still reads the same.
    versions = [PROGRAM_DOC.read_bytes().replace(b"\r\n", b"\n")]
    commit = (doc.get("code") or {}).get("commit")
    if commit:
        r = subprocess.run(["git", "-C", str(ROOT), "show",
                            f"{commit}:./docs/efv-v2/PROGRAM.md"], capture_output=True)
        if r.returncode == 0:
            versions.append(r.stdout.replace(b"\r\n", b"\n"))
    assert cp["sha256"] in {hashlib.sha256(v).hexdigest() for lf in versions
                            for v in (lf, lf.replace(b"\n", b"\r\n"))}


# ---------------------------------------------------------------------------
# 4. no score anywhere

def test_the_artifact_carries_no_score_key(doc):
    bad = sorted({k for k in _walk_keys(doc, []) if _SCORE_KEY.search(k)})
    assert not bad, bad


def test_the_tool_computes_no_rater_score():
    src = TOOL.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for bad in ("spearmanr", "roc_auc", "_spearman", "_auc(", "import numpy",
                "import scipy", "efv_v2_stat", "bootstrap", "fv_published\"] >",
                "consensus_fv\"] >"):
        assert bad not in code, bad


def test_the_tool_groups_nothing_by_grade():
    """The same scan test_efv_v2_drivers.py runs on the identity modules; `strata`
    is the whitelist the spec names and is allowed."""
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    banned = ("groupby", "tier", "bucket", "cell", "by_fv", "fv_band", "fv_bin")
    grid = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in banned), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in grid, (node.value, node.lineno)


# ---------------------------------------------------------------------------
# the copied numbers and the derived curve

def test_faithfulness_numbers_are_copied_from_program_md(C, doc):
    faith = C._program_faithfulness(PROGRAM_DOC.read_text(encoding="utf-8"))
    rows = {r["label_view"]: r for r in doc["label_views"]["rows"]}
    assert [r["label_view"] for r in doc["label_views"]["rows"]] == \
        ["L6", "W3", "W2", "R3", "first_2"]
    for view, key in (("W3", "w3"), ("first_2", "first_2")):
        f = rows[view]["faithfulness_to_six_season"]
        assert f["hit"] == faith[key]["hit"] and f["pit"] == faith[key]["pit"]
        assert f["section"] == faith[key]["section"]
        assert f["path"] == "docs/efv-v2/PROGRAM.md"
    for view in ("L6", "W2", "R3"):
        f = rows[view]["faithfulness_to_six_season"]
        assert f["hit"] is None and f["pit"] is None


def test_label_views_resolve_by_the_lag_rule(doc):
    rt = doc["label_views"]["resolved_through"]
    assert rt == doc["label"]["resolved_through"]
    vint = sorted({r["vintage"] for r in doc["frame"]["rows"]})
    coh = [r["debut_cohort"] for r in doc["debut_cohorts"]["rows"]]
    lags = {"W3": 5, "W2": 4, "R3": 3}
    for r in doc["label_views"]["rows"]:
        v = r["label_view"]
        if v in lags:
            assert r["resolved_at_rt"]["vintages"] == [x for x in vint if x + lags[v] <= rt]
            assert r["added_at_rt_plus_1"]["vintages"] == \
                [x for x in vint if x + lags[v] == rt + 1]
        else:
            lag = {"L6": 5, "first_2": 1}[v]
            assert r["resolved_at_rt"]["debut_cohorts"] == [x for x in coh if x + lag <= rt]
            assert r["added_at_rt_plus_1"]["debut_cohorts"] == \
                [x for x in coh if x + lag == rt + 1]
    first2 = next(r for r in doc["label_views"]["rows"] if r["label_view"] == "first_2")
    # the look-1 cohort enters at RT + 1 as a count only
    assert first2["added_at_rt_plus_1"]["debut_cohorts"] == [F.R_VM_FIRST_DEBUT_YEAR]


def test_floor_curve_is_the_stated_formula(C, doc):
    fc = doc["floor_curve"]
    assert fc["z95"] == 1.645
    assert fc["n"] == list(C.N_CURVE)
    assert sorted(fc["n"]) == sorted([829, 858, 995, 1179, 1266, 1464, 1864, 149, 176,
                                      210, 2667, 5529])
    ids = {r["id"] for r in fc["references"]}
    assert ids == {"vm_econd_within", "lv_econd_within", "vm_erefit_pooled"}
    for ref in fc["references"]:
        assert ref["sha256"] and ref["path"].startswith("data/")
        assert ref["estimator"] in ("E_cond", "E_refit")
        for n in fc["n"]:
            want = round(1.645 * ref["sd_ref"] * math.sqrt(ref["n_ref"] / n), 4)
            assert fc["curve"][ref["id"]][str(n)] == want
    # the references really are the committed artifacts' own numbers
    ds16 = json.loads((ROOT / "data" / "efv_v2_dev_eval.json").read_text(encoding="utf-8"))["ds16"]
    leg = ds16["frames"]["vm_dev"]["deltas"]["v2_vs_prospx_consensus"]["spearman"]
    ref = next(r for r in fc["references"] if r["id"] == "vm_econd_within")
    assert ref["sd_ref"] == leg["sd"] and ref["n_ref"] == leg["n"]
    h2h = json.loads((ROOT / "data" / "xfv_headtohead_frame_eval.json").read_text(encoding="utf-8"))
    ref = next(r for r in fc["references"] if r["id"] == "vm_erefit_pooled")
    assert ref["sd_ref"] == h2h["vintage_matched"]["sd"]
    assert ref["n_ref"] == h2h["point"]["vintage_matched"]["n_rows"]


def test_debut_cohort_counts_on_a_fixture(C):
    pts_in = [{"snapshot_date": "2019-02-10", "consensus_fv": 1.0,
               "per_source": {"fangraphs": {"fv_published": 1.0},
                              "mlb_pipeline": {"fv_published": 1.0}}}]
    pts_out = [{"snapshot_date": "2018-08-10", "consensus_fv": 1.0,
                "per_source": {"fangraphs": {"fv_published": 1.0}}}]
    pts_after = [{"snapshot_date": "2019-04-20", "consensus_fv": 1.0,
                  "per_source": {"mlb_pipeline": {"fv_published": 1.0}}}]
    debuts = [{"player_key": "a", "debut_date": "2019-06-01", "mlbam_id": 1, "points": pts_in},
              {"player_key": "b", "debut_date": "2019-06-01", "points": pts_out},
              # debuted on 2019-04-15: the window closes at the debut day, so the
              # 2019-04-20 read is after it
              {"player_key": "c", "debut_date": "2019-04-15", "points": pts_after},
              {"player_key": "d", "debut_date": "2010-05-01", "points": []},
              {"player_key": "e", "debut_date": None, "points": []}]
    out = C.debut_cohorts_census(debuts, career_war_keys={"a", "c"})
    row = next(r for r in out["rows"] if r["debut_cohort"] == 2019)
    assert row == {"debut_cohort": 2019, "debuts": 3, "in_window_consensus_read": 1,
                   "fangraphs_and_pipeline_both": 1, "with_career_war_row": 2,
                   "with_record_id": 1, "reserved_vm": False}
    assert out["outside_cohort_range"] == {"2010": 1} and out["undated"] == 1
    assert [r["debut_cohort"] for r in out["rows"]] == list(range(2011, 2027))
    assert all(r["reserved_vm"] == (r["debut_cohort"] >= F.R_VM_FIRST_DEBUT_YEAR)
               for r in out["rows"])


def test_identity_join_routes_on_a_fixture(C):
    table = {"a": {"source": "ewar_v2"}, "b": {"source": "ewar_v2"},
             "c": {"source": "bbref"}, "d": {"source": "bbref"}}
    debuts = [{"player_key": "a", "mlbam_id": 1}, {"player_key": "b"},
              {"player_key": "c"}]
    out = C.identity_join_census(table=table, debuts=debuts, overrides={"b": 2})
    assert out["by_provider"]["ewar_v2"]["id_route"] == {
        "debuts_json_id": 1, "override_asset_id": 1, "no_id": 0, "key_not_in_debuts": 0}
    assert out["by_provider"]["bbref"]["id_route"] == {
        "debuts_json_id": 0, "override_asset_id": 0, "no_id": 1, "key_not_in_debuts": 1}
    assert out["rows"] == 4 and out["default_provider"] == war_source.DEFAULT_PROVIDER


# ---------------------------------------------------------------------------
# 5. the epoch stamp and the ledger row

def test_the_census_stamps_the_label_epoch(doc):
    assert doc["label"]["provider"] == war_source.DEFAULT_PROVIDER
    assert doc["label"]["resolved_through"] == int(D.RESOLVED_THROUGH)
    assert doc["label"]["resolved_through_plus_1"] == int(D.RESOLVED_THROUGH) + 1
    assert doc["identity_join"]["default_provider"] == war_source.DEFAULT_PROVIDER
    assert "new census" in doc["epoch"]
    assert doc["generated_at"] and doc["produced_by"] == "tools/efv_label_pool_census.py"
    assert doc["role"] == "development" and doc["model_id"] == "efv_label_pool"


def _assert_census_row(row, doc):
    assert row["model_id"] == "efv_label_pool"
    assert row["role"] == "development" and row["tilted"] is False
    assert row["frame"] == "lv_dev" and P.FRAMES["lv_dev"]["role"] == "development"
    assert row["raters"] == {} and row["deltas"] == {}
    assert row["resolvable"] is None and row["share"] is None
    assert row["note"] == "label pool census, no score"
    assert row["n"] == doc["frame"]["dev_totals"]["rows"]
    assert row["n_by_side"] == doc["frame"]["dev_totals"]["by_side"]
    assert row["model_version"]["resolved_through"] == doc["label"]["resolved_through"]
    assert row["model_version"]["provider"] == doc["label"]["provider"]
    assert row["sources"][0]["path"].endswith("efv_label_pool_census.json")
    assert row["sources"][0]["sha256"] and row["sources"][0]["generated_at"]
    assert row["content_hash"] == P.content_hash(row)
    assert row["trigger"] in P.TRIGGERS


def test_ledger_row_is_counts_only_and_appends_once(C, doc, tmp_path):
    art = tmp_path / "efv_label_pool_census.json"
    art.write_text(json.dumps(doc), encoding="utf-8")
    now = "2026-10-02T00:00:00Z"
    row = C.ledger_row(doc, art, now_iso=now)
    _assert_census_row(row, doc)
    out, led = tmp_path / "efv_progress.json", tmp_path / "ledger.jsonl"
    res = P.commit_rows([row], data_dir=tmp_path, out_path=out, ledger_path=led,
                        sb=None, now_iso=now)
    assert res["appended"] == [row["run_id"]] and res["n_rows"] == 1
    res2 = P.commit_rows([C.ledger_row(doc, art, now_iso=now)], data_dir=tmp_path,
                         out_path=out, ledger_path=led, sb=None, now_iso=now)
    assert res2["appended"] == [] and res2["n_rows"] == 1
    written = json.loads(out.read_text(encoding="utf-8"))["rows"]
    assert len(written) == 1
    _assert_census_row(written[0], doc)


def test_served_ledger_carries_the_census_row(doc):
    if not PROG.exists():
        pytest.skip("data/efv_progress.json not built")
    rows = [r for r in json.loads(PROG.read_text(encoding="utf-8"))["rows"]
            if r.get("model_id") == "efv_label_pool"]
    assert rows, "no efv_label_pool row in data/efv_progress.json"
    _assert_census_row(rows[-1], doc)
    assert rows[-1]["sources"][0]["path"] == "data/efv_label_pool_census.json"
