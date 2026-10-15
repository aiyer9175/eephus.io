# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV X5 pins (docs/efv-v2/EFV_X5_OLDER_VINTAGES.md).

1. No ingested point is dated after its list publication: every point's snapshot_date is
   its published_on, inside its list year's preseason window, and every archive capture
   is at or after the publication.
2. No list is dated in a reserved year and no vintage is outside 2006 to 2019.
3. The new source keys are not scored and no served module names them.
4. The module reads no outcome (no label or WAR import) and groups nothing by
   consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).
5. The resolver index a row of vintage V reads ends at V - 1, and a resolved id with a
   major league line before V is not a member.
6. The parsers keep list facts only (the later stat line on BA's all-time page is never
   read) and a numbered comment thread never extends a list.
7. The census artifact's floors follow the registered formula, and only eligible lists
   reach the points artifact.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import efv_identity as ID
import efv_vintage_frame as F
import efv_x5_older_vintages as X
import source_backtest as SB

ROOT = Path(__file__).parent
_HAVE_POINTS = X.POINTS_PATH.exists()
_HAVE_CENSUS = X.CENSUS_PATH.exists()


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1, 2: dating

@pytest.mark.skipif(not _HAVE_POINTS, reason="points artifact not built")
def test_no_point_dated_after_its_list_publication():
    doc = _load(X.POINTS_PATH)
    recs = doc["records"]
    assert recs, "the points artifact holds no record"
    assert X.point_violations(recs) == []
    n = 0
    for rec in recs:
        for p in rec["points"]:
            for src, ps in p["per_source"].items():
                pub = ps["published_on"]
                assert p["snapshot_date"] <= pub and p["snapshot_date"] == pub
                assert X.in_window(pub, ps["list_year"]), (rec["player_key"], pub)
                cap = X.capture_day(ps.get("capture_ts"))
                assert cap is None or cap >= pub, (rec["player_key"], cap, pub)
                assert ps["date_basis"] in ("page_dateline", "capture_upper_bound")
                n += 1
    assert n == doc["n_points"]


@pytest.mark.skipif(not _HAVE_POINTS, reason="points artifact not built")
def test_no_reserved_or_out_of_range_vintage():
    doc = _load(X.POINTS_PATH)
    years = {ps["list_year"] for rec in doc["records"] for p in rec["points"]
             for ps in p["per_source"].values()}
    assert years
    assert min(years) >= X.FIRST_VINTAGE == ID.FIRST_INDEX_SEASON + 1
    assert max(years) <= X.LAST_VINTAGE == max(F.DEV_VINTAGES)
    assert not years & set(F.RESERVED_LV)
    assert all(int(p["snapshot_date"][:4]) < min(F.RESERVED_LV)
               for rec in doc["records"] for p in rec["points"])


def test_point_violations_catches_a_late_point():
    rec = {"player_key": "x5:ba_top100_hist:a", "points": [{
        "snapshot_date": "2009-03-01",
        "per_source": {"ba_top100_hist": {
            "published_on": "2009-02-24", "snapshot_date": "2009-03-01",
            "list_year": 2009, "capture_ts": "20090226153045"}}}]}
    assert any("not dated at its publication" in v for v in X.point_violations([rec]))
    rec["points"][0]["snapshot_date"] = "2009-02-24"
    rec["points"][0]["per_source"]["ba_top100_hist"]["snapshot_date"] = "2009-02-24"
    assert X.point_violations([rec]) == []
    rec["points"][0]["per_source"]["ba_top100_hist"]["capture_ts"] = "20090201000000"
    assert any("before publication" in v for v in X.point_violations([rec]))


def test_point_violations_catches_out_of_window_and_reserved():
    def one(pub, v):
        return [{"player_key": "k", "points": [{"snapshot_date": pub, "per_source": {
            "sickels_hist": {"published_on": pub, "snapshot_date": pub, "list_year": v,
                             "capture_ts": None}}}]}]
    assert any("outside the 2010 window" in v
               for v in X.point_violations(one("2009-12-20", 2010)))
    bad = X.point_violations(one("2020-02-01", 2020))
    assert any("reserved" in v for v in bad) and any("outside 2006" in v for v in bad)


# ---------------------------------------------------------------------------
# 3, 4: not scored, no outcome, no FV cell

def test_new_sources_not_scored_and_not_served():
    assert not X.NEW_SOURCE_KEYS & set(SB.SCORED_SOURCES)
    for mod in ("consensus.py", "source_backtest.py", "efv_export.py", "build_site.py"):
        text = (ROOT / mod).read_text(encoding="utf-8")
        for key in X.NEW_SOURCE_KEYS:
            assert key not in text, (mod, key)


_TREE = ast.parse((ROOT / "efv_x5_older_vintages.py").read_text(encoding="utf-8"))
_TOOL = ast.parse((ROOT / "tools" / "efv_x5_older_vintages.py").read_text(encoding="utf-8"))
_OUTCOME_MODULES = {"efv_labels", "war_source", "efv_model", "efv_v2_model", "efv_score",
                    "efv5_combined", "efv_v2_serve", "consensus"}


def _imports(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


def _attrs_of(tree, alias):
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == alias}


def test_module_and_tool_read_no_outcome():
    for tree in (_TREE, _TOOL):
        assert not _imports(tree) & _OUTCOME_MODULES
    # efv_dataset is read for its side routing only, the frame for its window, guard,
    # universe, frame builder and the major league id sets
    assert _attrs_of(_TREE, "D") == {"_side_match"}
    assert _attrs_of(_TREE, "F") <= {"DEV_VINTAGES", "SIDES", "RESERVED_LV",
                                     "guard_score_request", "_mlb_ids", "build_frame"}
    assert _attrs_of(_TOOL, "F") <= {"load_universe"}


_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED = ("groupby", "tier", "bucket", "cell", "stratum", "by_fv", "fv_band", "fv_bin")


def test_no_fv_cell_grouping():
    for node in ast.walk(_TREE):
        if isinstance(node, ast.Name):
            assert not any(t in node.id.lower() for t in _BANNED), node.id
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED), node.value


@pytest.mark.skipif(not _HAVE_CENSUS, reason="census artifact not built")
def test_census_strata_whitelist_and_no_score():
    doc = _load(X.CENSUS_PATH)
    assert doc["strata"] == ["source", "list_year", "vintage", "side", "id_how"]
    assert doc["served"] is False and doc["role"] == "development"
    banned = {"spearman", "auc", "delta", "war", "w3", "label", "rho", "efv", "consensus_fv"}

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    assert not set(keys(doc)) & banned


# ---------------------------------------------------------------------------
# 5: timing of the resolver and the major league check

def _rec(name, pos, pub, v):
    return {"player_key": X.record_key("ba_top100_hist", name), "player_name": name,
            "position": pos, "points": [{"snapshot_date": pub, "per_source": {
                "ba_top100_hist": {"rank": 1, "grade": None, "fv_published": None,
                                   "list_year": v, "published_on": pub,
                                   "snapshot_date": pub}}}]}


def test_resolver_index_ends_before_the_vintage(monkeypatch):
    calls = []

    def spy(last_season, **kw):
        calls.append(int(last_season))
        idx = ID.NameIndex()
        idx.add("Test Prospect", 111, int(last_season), "hitting", 300)
        return idx
    monkeypatch.setattr(ID, "build_index", spy)
    monkeypatch.setattr(F, "_mlb_ids", lambda s: frozenset())
    rows = X.augmented_rows([_rec("Test Prospect", "OF", "2009-02-24", 2009)], 2009)
    assert calls == [2008]
    assert [(r["side"], r["person_id"]) for r in rows] == [("hit", 111)]
    X.resolve_list_rows({"list_year": 2007, "rows": [{"name": "Test Prospect",
                                                       "pos": "of"}]})
    assert calls[-1] == 2006


def test_name_seen_only_in_v_is_not_a_candidate():
    idx = ID.NameIndex()
    idx.add("Late Arrival", 222, 2009, "pitching", 100)
    assert X.augmented_rows([_rec("Late Arrival", "RHP", "2009-02-24", 2009)], 2009,
                            index=idx) == []


def test_major_league_line_before_v_removes_the_row(monkeypatch):
    idx = ID.NameIndex()
    idx.add("Callup Guy", 333, 2007, "hitting", 400)
    rec = _rec("Callup Guy", "SS", "2009-02-24", 2009)
    monkeypatch.setattr(F, "_mlb_ids", lambda s: frozenset({333}) if s == 2008 else frozenset())
    assert X.augmented_rows([rec], 2009, index=idx) == []
    monkeypatch.setattr(F, "_mlb_ids", lambda s: frozenset({333}) if s == 2009 else frozenset())
    assert len(X.augmented_rows([rec], 2009, index=idx)) == 1


def test_point_outside_the_window_is_not_a_read(monkeypatch):
    idx = ID.NameIndex()
    idx.add("Early List", 444, 2007, "hitting", 400)
    monkeypatch.setattr(F, "_mlb_ids", lambda s: frozenset())
    rec = _rec("Early List", "C", "2008-12-05", 2009)
    assert X.augmented_rows([rec], 2009, index=idx) == []


def test_reserved_vintage_is_refused():
    with pytest.raises(ValueError):
        X.augmented_rows([], 2020, index=ID.NameIndex())


# ---------------------------------------------------------------------------
# 6: parsers

def test_ba_alltime_parser_drops_the_stat_column():
    page = ('<div id="2009"></div><tr><td><strong>1. <a href="#">Matt Wieters</a>, c, '
            'Orioles</strong></td><td><strong>.255/.330/.420, 900 games played</strong>'
            '</td></tr><tr><td><strong>2. David Price, lhp, Rays</strong></td>'
            '<td><strong>150-90, 3.30 ERA</strong></td></tr>')
    out = X.parse_ba_alltime(page)
    assert out == {2009: [{"rank": 1, "name": "Matt Wieters", "pos": "c", "team": "Orioles"},
                          {"rank": 2, "name": "David Price", "pos": "lhp", "team": "Rays"}]}
    assert "games" not in json.dumps(out) and "ERA" not in json.dumps(out)


def test_org10_parser_reads_dateline_and_list():
    page = ("<p>Sitemap</p><p>Atlanta Braves By Bill Ballew January 5, 2008</p>"
            "<p>TOP TEN PROSPECTS 1. Jordan Schafer, of 2. Jason Heyward, of "
            "3. Jair Jurrjens, rhp BEST TOOLS Best Hitter Jordan Schafer</p>")
    p = X.parse_ba_org10(page)
    assert p["published_on"] == "2008-01-05"
    assert [(r["rank"], r["name"], r["pos"]) for r in p["rows"]] == [
        (1, "Jordan Schafer", "of"), (2, "Jason Heyward", "of"), (3, "Jair Jurrjens", "rhp")]


def test_bp_parser_numbered_and_ordered():
    head = "<header>Kevin Goldstein | February 13, 2009 |</header>"
    numbered = (head + '<div class="article-content"><p>1. Matt Wieters, C, Orioles</p>'
                "<p>2. David Price, LHP, Rays</p><p>Thank you for reading</p></div>")
    p = X.parse_bp_top100(numbered)
    assert p["published_on"] == "2009-02-13"
    assert [r["name"] for r in p["rows"]] == ["Matt Wieters", "David Price"]
    ordered = (head.replace("February 13, 2009", "March 3, 2010")
               + '<div class="article-content"><ol><li>Stephen Strasburg, RHP, Nationals'
               "</li><li>Jason Heyward, OF, Braves</li></ol>Thank you for reading</div>")
    p = X.parse_bp_top100(ordered)
    assert p["published_on"] == "2010-03-03"
    assert [(r["rank"], r["name"]) for r in p["rows"]] == [(1, "Stephen Strasburg"),
                                                         (2, "Jason Heyward")]


def test_sickels_parser_stops_at_a_comment_list():
    page = ("<title>Pittsburgh Pirates Top 20 Prospects for 2009</title>"
            "<p>by John Sickels on Jan 1, 2009 7:32 PM EST</p>"
            "<p>1) Pedro Alvarez, 3B, Grade A-: text</p>"
            "<p>2) Andrew McCutchen, OF, Grade B+: text</p>"
            "<p>1) Someone Else, OF, Grade C: a reader's list</p>")
    p = X.parse_sickels(page)
    assert p["author"] == "John Sickels" and p["published_on"] == "2009-01-01"
    assert [(r["rank"], r["name"], r["grade"]) for r in p["rows"]] == [
        (1, "Pedro Alvarez", "A-"), (2, "Andrew McCutchen", "B+")]
    assert X.sickels_is_org_list(p["title"])
    assert X.sickels_is_org_list("St. Louis Cardinals Top 20+ Prospects for 2009")
    assert not X.sickels_is_org_list("Top 20 Shadow Twins Prospects")


# ---------------------------------------------------------------------------
# 7: census arithmetic and eligibility

@pytest.mark.skipif(not (_HAVE_CENSUS and _HAVE_POINTS), reason="artifacts not built")
def test_census_floors_and_eligibility():
    doc = _load(X.CENSUS_PATH)
    fl = doc["floors"]
    ref = fl["reference"]
    G = sum(r["gained"] for r in doc["frame"])
    assert G == fl["gained_rows"] > 0
    r = ref["n_ref"] / fl["n_current_resolved_2011_2019"]
    n_after = ref["n_ref"] + r * G
    assert fl["primary"]["n_after"] == pytest.approx(n_after, abs=0.1)
    assert fl["primary"]["mde95_after"] == pytest.approx(
        X.mde95(n_after, ref["sd_ref"], ref["n_ref"], ref["z95"]), abs=1e-5)
    assert fl["primary"]["mde95_after"] < fl["primary"]["mde95_before"]
    census_ref = _load(ROOT / "data" / "efv_label_pool_census.json")["floor_curve"]
    want = next(x for x in census_ref["references"] if x["id"] == X.FLOOR_REF_ID)
    assert (ref["sd_ref"], ref["n_ref"]) == (want["sd_ref"], want["n_ref"])
    for lst in doc["lists"]:
        if lst["eligible"]:
            assert lst["match_rate"] >= X.ELIGIBLE_MATCH_RATE
            assert X.in_window(lst["published_on"], lst["list_year"])
    ok = {(x["source"], x["list_year"], x["published_on"]) for x in doc["lists"]
          if x["eligible"]}
    pts = _load(X.POINTS_PATH)
    for rec in pts["records"]:
        for p in rec["points"]:
            for src, ps in p["per_source"].items():
                assert (src, ps["list_year"], ps["published_on"]) in ok
