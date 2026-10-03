# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/fwar_label_rebuild_check.py, precondition E7's independent label rebuild, on
fixtures only: nothing here reads prospects.db, data/fwar_vintage.json, the served matrices
or the network, and no receipt lands under data/.

Pinned: an exact match passes; one mismatched row in ten fails the 0.99 bar (and one in a
hundred sits exactly on it); an eWAR v2 matrix, an arm matrix and a stale stamp are refused
before anything is compared; the 0.0005 tolerance edge is inclusive; A1's shifted window and
stub, the censored tail and the terminal resolution are rebuilt from their written
definitions; a row with no id is a mismatch and is never stamped fwar; step C's resolver
order; the receipt path guard; and the independence guard (the module imports neither
efv_dataset nor war_source, and calls no production label function). Every expected label
below is worked by hand in its comment, not computed by the tool.
"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import fwar_vintage as FV                      # noqa: E402
import fwar_label_rebuild_check as T           # noqa: E402

TOOL = HERE / "tools" / "fwar_label_rebuild_check.py"
FIELDS = ["war", "rar", "numTeams"]


# ------------------------------------------------------------------ fixtures
def _grp(rows: dict, status: str = "frozen") -> dict:
    g = {"group": "x", "status": status, "fields": list(FIELDS),
         "rows": {str(k): [v, None, 1] for k, v in rows.items()}}
    g["content_sha256"] = FV.group_content_sha(g)
    return g


def _seal(seasons: dict) -> dict:
    """A fixture vintage whose hashes verify, built with fwar_vintage's own hash helpers."""
    blob = {"schema": FV.SCHEMA, "seasons": {}}
    for s, (hit, pit) in sorted(seasons.items()):
        sb = {"hitting": hit, "pitching": pit,
              "fetched_at": "2026-10-02T23:00:00+00:00"}
        sb["hitting"]["fetched_at"] = sb["pitching"]["fetched_at"] = sb["fetched_at"]
        sb["content_sha256"] = FV.season_content_sha(sb)
        blob["seasons"][str(s)] = sb
    blob["vintage_id"] = FV.vintage_id(blob)
    return blob


def _vintage(extra_hit: dict | None = None) -> dict:
    """Players:
      1001 hitter, two-way in 2020: 2018 1.234 -> 1.23; 2019 2.0; 2020 0.456 + 0.111 =
           0.567 -> 0.57; 2021 3.0; 2022 -0.5; 2023 1.0
      1002 hitter: 2022 1.0; 2023 2.0; 2024 0.5; no 2025 row
      2001 pitcher: 2019 0.75; 2020 1.25; 2021 2.0; 2022 0.0; 2023 1.0; 2024 0.5
      2002 pitcher (A1 fixture): 2022 0.4; 2023 1.0; 2024 2.0; no 2025 row
      3000..3099 hitters: 1.0 in every season 2015 to 2020
    """
    hit = {s: {} for s in range(2015, 2026)}
    pit = {s: {} for s in range(2015, 2026)}
    for s, v in {2018: 1.234, 2019: 2.0, 2020: 0.456, 2021: 3.0, 2022: -0.5, 2023: 1.0}.items():
        hit[s][1001] = v
    pit[2020][1001] = 0.111
    for s, v in {2022: 1.0, 2023: 2.0, 2024: 0.5}.items():
        hit[s][1002] = v
    for s, v in {2019: 0.75, 2020: 1.25, 2021: 2.0, 2022: 0.0, 2023: 1.0, 2024: 0.5}.items():
        pit[s][2001] = v
    for s, v in {2022: 0.4, 2023: 1.0, 2024: 2.0}.items():
        pit[s][2002] = v
    for mid in range(3000, 3100):
        for s in range(2015, 2021):
            hit[s][mid] = 1.0
    for (mid, s), v in (extra_hit or {}).items():
        hit[s][mid] = v
    return _seal({s: (_grp(hit[s]), _grp(pit[s])) for s in hit})


def _row(key, mlbam, dy, tr, tc, cens, w, nobs, **kw) -> dict:
    r = {"player_key": key, "kind": "debuted", "debut_year": dy, "cutoff": f"{dy}-04-02",
         "debut_date_is_placeholder": False, "target_resolved": tr, "target_censored": tc,
         "censored": cens, "weight": w, "observed_seasons": nobs, "mlbam_id": mlbam}
    r.update(kw)
    return r


def _bust(key) -> dict:
    return {"player_key": key, "kind": "bust", "debut_year": None, "target_resolved": 0.0,
            "target_censored": 0.0, "censored": False, "weight": 1.0, "observed_seasons": 6}


def _report(rows, provider="fwar", rt=2025, acct=None) -> dict:
    return {"target": f"first-6-season summed WAR ({provider}); resolved<= {rt}",
            "accounting": dict(acct or {}),
            "counts": {"rows_total": len(rows),
                       "debuted": sum(1 for r in rows if r["kind"] == "debuted")}}


def _hit_rows() -> list:
    return [
        # 1001: window 2018-2023 all <= 2025, resolved: 1.23 + 2.0 + 0.57 + 3.0 - 0.5 + 1.0 = 7.30
        _row("a_hitter", 1001, 2018, 7.3, 7.3, False, 1.0, 6),
        # 1002: window 2022-2027, observed 2022-2025 (n=4): 1.0 + 2.0 + 0.5 + 0 = 3.5;
        # censored 3.5 + 2 * 3.5 / 4 = 5.25; weight round(4/6, 3) = 0.667
        _row("b_hitter", 1002, 2022, 3.5, 5.25, True, 0.667, 4),
        _bust("never_made_it"),
    ]


def _pit_rows() -> list:
    return [
        # 2001: window 2019-2024, resolved: 0.75 + 1.25 + 2.0 + 0.0 + 1.0 + 0.5 = 5.5
        _row("c_pitcher", 2001, 2019, 5.5, 5.5, False, 1.0, 6),
        _bust("pitching_bust"),
    ]


def _resolver(table: dict | None = None):
    return T.make_resolver(dict(table or {}), {}, {})


def _sides(hit=None, pit=None, hit_report=None, pit_report=None) -> dict:
    hit = _hit_rows() if hit is None else hit
    pit = _pit_rows() if pit is None else pit
    return {"hit": (hit, hit_report or _report(hit)), "pit": (pit, pit_report or _report(pit))}


def _bulk(n: int, bad: int = 0, bad_value: float = 6.5) -> list:
    """n hitters 3000.. with a flat 1.0 per season 2015-2020: label 6.0 each; the first
    `bad` rows carry bad_value instead."""
    return [_row(f"bulk_{i}", 3000 + i, 2015, bad_value if i < bad else 6.0,
                 bad_value if i < bad else 6.0, False, 1.0, 6) for i in range(n)]


# ------------------------------------------------------------------ the five the spec names
def test_exact_match_passes():
    rec = T.check(_sides(), _vintage(), _resolver())
    for s, n in (("hit", 2), ("pit", 1)):
        side = rec["sides"][s]
        assert side["rows_compared"] == n and side["rows_matched"] == n
        assert side["match_share"] == 1.0 and side["passed"]
        assert side["war_basis"] == {"fwar": n, "mixed": 0}
        assert side["mismatches"] == []
    assert rec["passed"] and rec["pass_line"].startswith("E7 PASS")
    assert rec["tolerance"] == 0.0005
    assert T.format_lines(rec)[-1].startswith("E7 PASS")


def test_one_row_mismatch_below_the_bar_fails(tmp_path):
    hit = _bulk(10, bad=1)
    rec = T.check(_sides(hit=hit), _vintage(), _resolver())
    side = rec["sides"]["hit"]
    assert (side["rows_compared"], side["rows_matched"], side["match_share"]) == (10, 9, 0.9)
    assert not side["passed"] and rec["sides"]["pit"]["passed"] and not rec["passed"]
    assert rec["pass_line"].startswith("E7 FAIL")
    (m,) = side["mismatches"]
    assert m["key"] == "bulk_0" and m["mlbam"] == 3000 and m["debut_year"] == 2015
    assert m["fields"] == ["target_resolved", "target_censored"]
    assert m["matrix"]["target_resolved"] == 6.5 and m["rebuilt"]["target_resolved"] == 6.0
    assert m["seasons"] == {str(y): 1.0 for y in range(2015, 2021)}
    assert any(line.startswith("    MISMATCH hit bulk_0") for line in T.format_lines(rec))
    # through main: exit 1, and the receipt carries the same FAIL line
    paths = _write_inputs(tmp_path, _sides(hit=hit), _vintage())
    out = tmp_path / "out" / "e7_receipt.json"
    assert T.main(["--receipt", str(out)], resolver=_resolver(), **paths) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["pass_line"].startswith("E7 FAIL")


def test_one_mismatch_in_a_hundred_sits_on_the_bar():
    rec = T.check(_sides(hit=_bulk(100, bad=1)), _vintage(), _resolver())
    assert rec["sides"]["hit"]["match_share"] == 0.99 and rec["passed"]
    rec = T.check(_sides(hit=_bulk(100, bad=2)), _vintage(), _resolver())
    assert rec["sides"]["hit"]["match_share"] == 0.98 and not rec["passed"]


def test_ewar_v2_matrix_is_refused(tmp_path):
    sides = _sides()
    pit = sides["pit"][0]
    sides["pit"] = (pit, _report(pit, provider="ewar_v2"))
    with pytest.raises(T.CheckRefused, match="ewar_v2"):
        T.check(sides, _vintage(), _resolver())
    paths = _write_inputs(tmp_path, sides, _vintage())
    out = tmp_path / "out" / "e7_receipt.json"
    assert T.main(["--receipt", str(out)], resolver=_resolver(), **paths) == 2
    assert not out.exists()


def test_tolerance_edge_is_half_the_stored_precision_inclusive():
    for value, ok in ((6.0005, True), (5.9995, True), (6.0006, False), (6.001, False)):
        hit = [_row("edge", 3000, 2015, value, value, False, 1.0, 6)]
        rec = T.check(_sides(hit=hit), _vintage(), _resolver())
        assert rec["sides"]["hit"]["rows_matched"] == int(ok), value
    hit = [_row("edge_w", 1002, 2022, 3.5, 5.25, True, 0.6665, 4)]     # 0.667 - 0.0005
    assert T.check(_sides(hit=hit), _vintage(), _resolver())["sides"]["hit"]["rows_matched"] == 1
    hit = [_row("edge_w", 1002, 2022, 3.5, 5.25, True, 0.666, 4)]
    m = T.check(_sides(hit=hit), _vintage(), _resolver())["sides"]["hit"]["mismatches"]
    assert m[0]["fields"] == ["weight"]


def test_independence_guard_no_production_label_path():
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    banned = {"efv_dataset", "war_source", "rebase_career_war", "stats", "efv_model"}
    assert not imported & banned, imported & banned
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            called.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    assert not called & {"_label_6yr", "_label_seasons", "build_matrix", "season_totals",
                         "side_targets", "fwar_index", "fwar_seasons_from_incumbent",
                         "load_career_war", "career_war_bulk"}
    # at run time: the tool and its default resolver's module leave both unimported
    code = ("import sys; sys.path[:0] = [r'%s', r'%s'];"
            "import fwar_label_rebuild_check, rebase_career_war_to_ewar;"
            "bad = [m for m in ('war_source', 'efv_dataset') if m in sys.modules];"
            "print(bad); sys.exit(1 if bad else 0)") % (HERE / "tools", HERE)
    res = subprocess.run([sys.executable, "-c", code], cwd=str(HERE),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr


# ------------------------------------------------------------------ the definitions
def test_a1_shifted_window_stub_and_tail():
    acct = {"debuted_window_shifted": 1}
    pit = [
        # 2002, debut day 2022-08-10 after 04-15: window 2023-2028, observed 2023-2025
        # (n=3): 1.0 + 2.0 + 0 = 3.0, stub 2022 = 0.4, obs_sum 3.4; tail rate
        # (3.4 - 0.4) / 3 = 1.0; censored 3.4 + 3 * 1.0 = 6.4; weight 0.5
        _row("late_debut", 2002, 2022, 3.4, 6.4, True, 0.5, 3, cutoff="2022-08-10"),
        # the same player with a placeholder day: no shift, window 2022-2027, observed
        # 2022-2025 (n=4): 0.4 + 1.0 + 2.0 + 0 = 3.4; censored 3.4 + 2 * 0.85 = 5.1
        _row("placeholder", 2002, 2022, 3.4, 5.1, True, 0.667, 4, cutoff="2022-08-10",
             debut_date_is_placeholder=True),
    ]
    rec = T.check(_sides(pit=pit, pit_report=_report(pit, acct=acct)), _vintage(), _resolver())
    assert rec["sides"]["pit"]["rows_matched"] == 2, rec["sides"]["pit"]["mismatches"]
    assert rec["sides"]["pit"]["stamp"]["service_aligned"] is True
    # with A1 off in the report, the late debut no longer shifts and stops matching
    rec = T.check(_sides(pit=pit), _vintage(), _resolver())
    assert [m["key"] for m in rec["sides"]["pit"]["mismatches"]] == ["late_debut"]


def test_terminal_resolution_rule():
    hit = [
        # 1002 retired 2025-06-01 (<= RESOLVED_THROUGH): resolves at the observed 3.5
        _row("retired", 1002, 2022, 3.5, 3.5, False, 1.0, 6, terminal_resolved="2025-06-01"),
        # retired 2026-03-15 (pre-season of RESOLVED_THROUGH + 1): resolves too
        _row("retired_pre", 1002, 2022, 3.5, 3.5, False, 1.0, 6, terminal_resolved="2026-03-15"),
        # a matrix that resolved on a mid-2026 date contradicts the rule: mismatch
        _row("retired_mid", 1002, 2022, 3.5, 3.5, False, 1.0, 6, terminal_resolved="2026-06-15"),
    ]
    side = T.check(_sides(hit=hit), _vintage(), _resolver())["sides"]["hit"]
    assert side["rows_matched"] == 2
    (m,) = side["mismatches"]
    assert m["key"] == "retired_mid"
    assert set(m["fields"]) == {"target_censored", "censored", "weight", "observed_seasons"}


def test_postseason_redate_and_rerouted_rows_read_no_day():
    assert T.label_date_of({"debut_year": 2021, "cutoff": "2020-10-01"}) is None
    assert T.label_date_of({"debut_year": 2020, "cutoff": "2020-01-01",
                            "rerouted_from_bust": True}) is None
    assert T.label_date_of({"debut_year": 2020, "cutoff": "2020-08-01"}) == "2020-08-01"
    assert T.service_window_shifts("2020-04-16") and not T.service_window_shifts("2020-04-15")


def test_no_id_row_is_a_mismatch_and_never_fwar():
    hit = _hit_rows() + [_row("ghost", None, 2018, 1.0, 1.0, False, 1.0, 6)]
    side = T.check(_sides(hit=hit), _vintage(), _resolver())["sides"]["hit"]
    assert side["rows_compared"] == 3 and side["rows_matched"] == 2
    (m,) = side["mismatches"]
    assert (m["key"], m["reason"], m["war_basis"], m["rebuilt"]) == ("ghost", "no_id", "mixed", None)
    assert side["war_basis"] == {"fwar": 2, "mixed": 1}


def test_mixed_season_is_not_served_and_stamps_mixed():
    v = _vintage()
    # 2015 pitching recorded absent: 2015 is no longer an fwar season of the vintage
    v["seasons"]["2015"]["pitching"] = _grp({}, "absent")
    sb = v["seasons"]["2015"]
    sb["content_sha256"] = FV.season_content_sha(sb)
    v["vintage_id"] = FV.vintage_id(v)
    # the bulk hitter's 2015 season is not read: 1.0 * 5 = 5.0
    hit = [_row("bulk_0", 3000, 2015, 5.0, 5.0, False, 1.0, 6)]
    side = T.check(_sides(hit=hit), v, _resolver())["sides"]["hit"]
    assert side["rows_matched"] == 1 and side["war_basis"] == {"fwar": 0, "mixed": 1}


def test_resolver_order_and_disagreement_is_reported():
    r = T.make_resolver({"k": 1}, {"k": 2, "p": 3}, {"k": 4, "p": 5, "o": 6})
    assert r("k", 9) == (1, "label_join") and r("p", 9) == (3, "photos")
    assert r("o", 9) == (6, "override") and r("x", 9) == (9, "matrix_row")
    assert r("x", None) == (None, None)
    # a label-join id that differs from the row's own is used and listed
    hit = [_row("rebound", 999, 2018, 7.3, 7.3, False, 1.0, 6)]
    side = T.check(_sides(hit=hit), _vintage(), _resolver({"rebound": 1001}))["sides"]["hit"]
    assert side["rows_matched"] == 1
    assert side["id_differs_from_row"] == [["rebound", 999, 1001, "label_join"]]


def test_written_definitions_agree_with_the_production_label_on_synthetic_inputs(monkeypatch):
    """Parity, not dependence: only this TEST imports efv_dataset. On a synthetic grid
    (no matrix, no career_war) the re-implemented window, censoring, A1 and terminal rules
    return what _label_6yr and _terminal_resolves return, at both resolution clocks and
    with A1 off and on."""
    import efv_dataset as ed
    patterns = [
        {},
        {y: 1.0 for y in range(2005, 2030)},
        {2011: 0.37, 2012: -0.41, 2014: 2.24, 2016: 5.03, 2019: -1.1, 2021: 0.01,
         2022: 3.33, 2023: 0.66, 2024: 1.9, 2025: -0.2, 2026: 4.44},
    ]
    dates = [None, "2016-04-15", "2016-04-16", "2016-09-28"]
    for rt in (2025, 2026):
        for a1 in (False, True):
            monkeypatch.setattr(ed, "RESOLVED_THROUGH", rt)
            monkeypatch.setattr(ed, "SERVICE_ALIGNED_WINDOW", a1)
            for seasons in patterns:
                for dy in range(2011, rt):
                    for d in dates:
                        day = None if d is None else f"{dy}{d[4:]}"
                        want = ed._label_6yr(seasons, dy, day)
                        got = T.rebuild_label(seasons, dy, day, resolved_through=rt,
                                              target_seasons=ed.TARGET_SEASONS,
                                              service_aligned=a1)
                        assert (got["target_resolved"], got["target_censored"],
                                got["censored"], got["weight"],
                                got["observed_seasons"]) == want, (rt, a1, dy, day)
            for td in ("2024-12-31", f"{rt}-09-30", f"{rt + 1}-04-01", f"{rt + 1}-04-02",
                       f"{rt + 2}-01-01", None, "bad"):
                assert T.terminal_resolves(td, rt) == ed._terminal_resolves(td), (rt, td)
    assert T.SERVICE_YEAR_CUT_MMDD == ed._SERVICE_YEAR_CUT_MMDD


# ------------------------------------------------------------------ refusals and the receipt
def test_arm_matrix_and_stale_stamp_are_refused():
    sides = _sides()
    hit = sides["hit"][0]
    sides["hit"] = (hit, _report(hit, acct={"label_seasons_key": "seasons_ewar_v2"}))
    with pytest.raises(T.CheckRefused, match="arm build"):
        T.check(sides, _vintage(), _resolver())
    sides = _sides()
    stale = _report(_pit_rows() + [_bust("extra")])
    sides["pit"] = (_pit_rows(), stale)
    with pytest.raises(T.CheckRefused, match="does not describe"):
        T.check(sides, _vintage(), _resolver())
    with pytest.raises(T.CheckRefused, match="unreadable"):
        T.read_stamp({"target": "first-6-season summed WAR"}, "hit")


def test_tampered_vintage_is_refused():
    v = _vintage()
    v["seasons"]["2018"]["hitting"]["rows"]["1001"][0] = 9.9
    with pytest.raises(T.CheckRefused, match="hash check"):
        T.check(_sides(), v, _resolver())


def test_receipt_path_guard_and_written_receipt(tmp_path):
    with pytest.raises(T.CheckRefused):
        T.assert_receipt_path(T.DATA / "e7_receipt.json")
    with pytest.raises(T.CheckRefused):
        T.assert_receipt_path(T.DATA / "sources" / "e7_receipt.json")
    assert T.assert_receipt_path(T.RECEIPT_PATH) == T.RECEIPT_PATH.resolve()
    assert T.RECEIPT_PATH.relative_to(T.LABS_ROOT) == Path("fwar_epoch_arms/e7_receipt.json")
    paths = _write_inputs(tmp_path, _sides(), _vintage())
    out = tmp_path / "out" / "e7_receipt.json"
    assert T.main(["--receipt", str(out)], resolver=_resolver(), **paths) == 0
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["schema"] == T.SCHEMA and rec["passed"] and rec["pass_line"].startswith("E7 PASS")
    assert rec["sides"]["hit"]["matrix_sha256"] and rec["vintage_id"]
    assert T.main(["--no-write"], resolver=_resolver(), **paths) == 0


def _write_inputs(tmp_path: Path, sides: dict, vintage: dict) -> dict:
    mp, rp = {}, {}
    for s, (rows, report) in sides.items():
        mp[s] = tmp_path / f"matrix_{s}.json"
        rp[s] = tmp_path / f"report_{s}.json"
        mp[s].write_text(json.dumps(rows, indent=0), encoding="utf-8")
        rp[s].write_text(json.dumps(report), encoding="utf-8")
    vp = tmp_path / "vintage.json"
    vp.write_text(json.dumps(copy.deepcopy(vintage)), encoding="utf-8")
    return {"matrix_paths": mp, "report_paths": rp, "vintage_path": vp}
