# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the team revealed-preference columns (efv_x2_revealed.py,
EFV_X2_REVEALED_PREFERENCE; registration docs/efv-v2/EFV_X2_REVEALED_PREFERENCE.md).

1. As of: a transaction announced on the read day or later, a MiLB season of the read's
   year, an invitation known on the read day and a bonus of the read's year never count;
   every value's latest input date is before the read.
2. The columns: promotion pace, age at promotion, in-season jumps and skipped levels;
   Rule 5 eligibility, protection, exposure and selection in each phase; options,
   releases, trades and the principal-piece rule; bonus over slot.
3. The fit: a constant column orders exactly as consensus (the delta is 0); a missing id
   never enters the slope fit.
4. Bans: reserved folds raise; nothing grouped by consensus-FV level; no served exporter
   imported; no column builder reads a label, WAR or debut; no em-dash; the fetch
   window.
5. The artifact, when present: a development read on the frozen label, B 2000, seed
   20261019, the two development frames only, every column read.
"""
from __future__ import annotations

import ast
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_vintage_frame as F  # noqa: E402
import efv_x2_revealed as X  # noqa: E402

SRC = ROOT / "efv_x2_revealed.py"
PID = 900201
MLB_A, MLB_B = 147, 121          # two major league clubs
AFF_A = 531                      # a minor league affiliate of MLB_A
TEAMS = {2015: {MLB_A: (1, MLB_A), MLB_B: (1, MLB_B), AFF_A: (12, MLB_A)},
         2016: {MLB_A: (1, MLB_A), MLB_B: (1, MLB_B), AFF_A: (12, MLB_A)}}


@pytest.fixture(autouse=True)
def _teams(monkeypatch):
    monkeypatch.setattr(X, "_TEAMS", TEAMS)


def _ev(day, code, desc="", frm=None, to=None, tid=None):
    return (day, code, desc, frm, to, tid)


def _milb(lines=None, medians=None, first=None, first_age=None):
    return X.MilbBook(lines or {"hit": {}, "pit": {}}, medians or {}, first or {},
                      first_age or {})


def _tx(events, *, trades=None, r5=None, detected=None):
    book = X.TxBook(events, trades or {}, r5 or {2015: "2015-12-10", 2016: "2016-12-08"},
                    ["2015-01"])
    book.r5_detected = detected or {y: True for y in book.r5_days}
    return book


def _books(*, events=None, milb=None, drafts=None, bonus=None, nri=None, trades=None,
           date_cap="2025-01-01"):
    return X.Books(_tx(events or {}, trades=trades), milb or _milb(), drafts or {},
                   bonus or {}, nri or {}, date_cap=date_cap)


# ---------------------------------------------------------------------------
# 1. as of
# ---------------------------------------------------------------------------

def test_nothing_on_or_after_the_read_counts():
    events = {PID: [_ev("2016-02-28", "OPT"), _ev("2016-03-01", "OPT"),
                    _ev("2016-03-02", "REL")]}
    nri = {PID: [("2016-02-01", 2016), ("2016-03-01", 2017)]}
    bonus = {PID: (2016, 0.4)}
    milb = _milb({"hit": {PID: {2015: [(2, 20.0, 300)], 2016: [(3, 21.0, 300)]}}, "pit": {}})
    b = _books(events=events, nri=nri, bonus=bonus, milb=milb)
    vals, dates = X.column_values(PID, "2016-03-01", None, "hit", b)
    assert vals["x2_options"] == 1.0 and vals["x2_release_events"] == 0.0
    assert vals["x2_nri_springs"] == 1.0
    assert vals["x2_bonus_vs_slot"] is None              # drafted in the read's year
    assert vals["x2_promos_per_season"] == 0.0           # 2016 not read in 2016
    assert all(d is None or d < "2016-03-01" for d in dates.values())


def test_no_id_no_date_or_a_read_past_the_cap_is_none():
    b = _books(events={PID: [_ev("2016-01-01", "OPT")]}, date_cap="2017-01-01")
    for pid, asof in ((None, "2016-03-01"), (PID, None), (PID, "2017-01-01")):
        vals, _d = X.column_values(pid, asof, None, "hit", b)
        assert all(v is None for v in vals.values())


# ---------------------------------------------------------------------------
# 2. the columns
# ---------------------------------------------------------------------------

def test_promotion_columns():
    seasons = {2012: [(1, 18.0, 150)],                    # entry, CPX
               2013: [(2, 19.0, 300), (3, 19.0, 120)],    # A, then A+ inside the season
               2014: [(5, 20.0, 400)],                    # AAA from A+: skips AA
               2015: [(5, 21.0, 400)]}
    med = {("hit", 2013, 2): 20.0, ("hit", 2013, 3): 21.0, ("hit", 2014, 5): 25.0}
    out, last = X.promotion_values(seasons, med, "hit", 2016)
    assert out["x2_promos_per_season"] == pytest.approx(3 / 4)
    assert out["x2_promo_age_rel"] == pytest.approx(((19 - 20) + (19 - 21) + (20 - 25)) / 3)
    assert out["x2_midseason_jumps"] == pytest.approx(1 / 4)
    assert out["x2_skipped_levels"] == 1.0               # AA, jumped from A+ (full season)
    assert last == "2015-12-31"
    out2, _ = X.promotion_values(seasons, med, "hit", 2014)
    assert out2["x2_promos_per_season"] == pytest.approx(2 / 2)
    empty, d = X.promotion_values({}, med, "hit", 2016)
    assert all(v is None for v in empty.values()) and d is None


def test_complex_to_full_season_is_not_a_skip():
    out, _ = X.promotion_values({2012: [(0, 17.0, 100)], 2013: [(3, 18.0, 300)]}, {},
                                "hit", 2014)
    assert out["x2_skipped_levels"] == 0.0 and out["x2_promo_age_rel"] is None


def test_rule5_first_eligible_year():
    milb = _milb(first={1: 2010, 2: 2010, 3: 2011, 4: 2011}, first_age={3: 17.0, 4: 20.0})
    drafts = {1: [2010], 2: [2008, 2010]}
    # high-school draftee, 18 on 5 June of the draft year: fifth draft (S + 4)
    assert X.rule5_first_year(1, "1992-01-15", milb, drafts) == (2014, "draft")
    # college draftee, 21: fourth draft (S + 3); the last draft year at or before entry
    assert X.rule5_first_year(2, "1989-01-15", milb, drafts) == (2013, "draft")
    # international signee, 17 in his first season: signed the year before, S + 4
    assert X.rule5_first_year(3, None, milb, drafts) == (2014, "ifa")
    # older international signee: signed in his first season, S + 3
    assert X.rule5_first_year(4, None, milb, drafts) == (2014, "ifa")
    assert X.rule5_first_year(5, None, milb, drafts) == (None, "no_milb_season")
    # a first season in the read's year or later is not known at the read
    assert X.rule5_first_year(1, "1992-01-15", milb, drafts, before_year=2010) == (
        None, "no_milb_season")
    assert X.rule5_first_year(1, "1992-01-15", milb, drafts, before_year=2011)[0] == 2014


def test_rule5_protection_exposure_and_selection():
    milb = _milb(first={PID: 2012, PID + 1: 2012, PID + 2: 2012})
    drafts = {PID: [2012], PID + 1: [2012], PID + 2: [2012]}
    birth = "1990-01-01"                                  # 22 at signing: S + 3 = 2015
    events = {
        # added in November 2015 before his first eligible draft (2015-12-10)
        PID: [_ev("2015-11-20", "SE", "", AFF_A, MLB_A)],
        # exposed in 2015, taken by a major league club on the 2016 draft day
        PID + 1: [_ev("2016-12-08", "CLW", "", AFF_A, MLB_B)],
        # exposed in 2015, taken by a minor league club on the 2015 draft day
        PID + 2: [_ev("2015-12-10", "CLW", "", MLB_B, AFF_A)],
    }
    b = _books(events=events, milb=milb, drafts=drafts)
    v0, _ = X.column_values(PID, "2017-02-01", birth, "hit", b)
    assert v0["x2_add_before_elig"] == 1.0 and v0["x2_r5_protect"] == 1.0
    assert v0["x2_r5_exposed_n"] == 0.0 and v0["x2_r5_selected"] == 0.0
    v1, _ = X.column_values(PID + 1, "2017-02-01", birth, "hit", b)
    assert v1["x2_add_before_elig"] == 0.0 and v1["x2_r5_protect"] == -1.0
    assert v1["x2_r5_exposed_n"] == 2.0 and v1["x2_r5_selected"] == 1.0
    assert v1["x2_r5m_selected"] == 0.0
    v2, _ = X.column_values(PID + 2, "2016-02-01", birth, "hit", b)
    assert v2["x2_r5m_selected"] == 1.0 and v2["x2_r5_selected"] == 0.0
    # before any eligible draft day: protection 0, nothing exposed
    v3, _ = X.column_values(PID + 1, "2015-06-01", birth, "hit", b)
    assert v3["x2_r5_protect"] == 0.0 and v3["x2_r5_exposed_n"] == 0.0


def test_an_undetected_draft_day_reads_selections_from_codes_only():
    b = _books(events={PID: [_ev("2015-12-10", "CLW", "", AFF_A, MLB_B)]})
    b.tx.r5_detected = {2015: False, 2016: True}
    v, _ = X.column_values(PID, "2016-02-01", None, "hit", b)
    assert v["x2_r5_selected"] == 0.0 and v["x2_r5m_selected"] == 0.0


def test_the_trade_principal_rule():
    mlb = {2016: frozenset({555}), 2015: frozenset()}
    trades = {77: [(PID,) + _ev("2016-07-30", "TR", "", AFF_A, MLB_B, 77),
                   (555,) + _ev("2016-07-30", "TR", "", MLB_B, MLB_A, 77)],
              78: [(PID,) + _ev("2016-07-30", "TR", "", AFF_A, MLB_B, 78),
                   (556,) + _ev("2016-07-30", "TR", "", AFF_A, MLB_B, 78),
                   (557,) + _ev("2016-07-30", "TR", "", MLB_A, MLB_B, 78),
                   (555,) + _ev("2016-07-30", "TR", "", MLB_B, MLB_A, 78)]}
    book = _tx({}, trades=trades)

    def season_mlb(y):
        return mlb.get(y, frozenset())
    ev = trades[77][0][1:]
    assert X.trade_principal(PID, ev, book, season_mlb=season_mlb)       # 1 for a major leaguer
    ev = trades[78][0][1:]
    assert not X.trade_principal(PID, ev, book, season_mlb=season_mlb)   # one of three sent
    # the trade season's line is not read when the read is in that season
    assert not X.trade_principal(PID, trades[77][0][1:], book, season_mlb=season_mlb,
                                 before_year=2016)
    assert X.trade_principal(PID, trades[77][0][1:], book, season_mlb=season_mlb,
                             before_year=2017)
    no_mlb = lambda y: frozenset()                                        # noqa: E731
    assert not X.trade_principal(PID, trades[77][0][1:], book, season_mlb=no_mlb)


def test_bonus_over_slot(tmp_path):
    p = tmp_path / "bonus.json"
    p.write_text(json.dumps({
        "1": {"year": 2017, "slot_usd": 1000000, "bonus_usd": 1500000},
        "2": {"year": 2018, "slot_usd": None, "bonus_usd": 250000},
        "3": {"year": 2016, "slot_usd": 500000, "bonus_usd": 500000},
        "4": {"year": 2019, "slot_usd": 500000, "bonus_usd": None}}), encoding="utf-8")
    b = X.load_bonus(p)
    assert b[1] == (2017, pytest.approx(math.log(1.5)))
    assert b[2] == (2018, pytest.approx(math.log(2.0)))   # over the late-round allowance
    assert 3 not in b and 4 not in b                      # no money before 2017; unsigned


def test_the_forty_man_replay():
    evs = [_ev("2015-11-20", "SE"), _ev("2016-04-01", "DES"), _ev("2016-05-01", "SFA",
           "x signed free agent y to a major league contract.")]
    assert not X.forty_man_on(evs, "2015-11-20") and X.forty_man_on(evs, "2015-11-21")
    assert not X.forty_man_on(evs, "2016-04-02") and X.forty_man_on(evs, "2016-05-02")
    assert X.first_add_day(evs, "2016-01-01") == "2015-11-20"
    assert X.first_add_day(evs, "2015-11-20") is None


# ---------------------------------------------------------------------------
# 3. the fit
# ---------------------------------------------------------------------------

def _fold(rng, n_tr=200, n_te=80, col=None):
    fv = rng.integers(35, 60, size=n_tr).astype(float)
    tr = [{"fv": float(fv[i]), "target": float(fv[i] / 10.0 + rng.normal()),
           "year": 2015 + (i % 2), "has_id": True,
           "x": {"c": col if col is not None else float(rng.normal())}} for i in range(n_tr)]
    te = [{"u": float(u), "x": {"c": col if col is not None else float(rng.normal())}}
          for u in rng.random(n_te)]
    return tr, te


def test_a_constant_column_orders_exactly_as_consensus():
    rng = np.random.default_rng(1)
    tr, te = _fold(rng, col=3.0)
    f = X.fit_fold(tr, te, ["c"])
    assert f["b_z"]["c"] == 0.0 and f["b_u"] > 0
    u = np.array([r["u"] for r in te])
    assert (np.argsort(f["score"], kind="stable") == np.argsort(u, kind="stable")).all()


def test_rows_without_an_id_never_enter_the_fit():
    rng = np.random.default_rng(2)
    tr, te = _fold(rng)
    f1 = X.fit_fold(tr, te, ["c"])
    extra = [dict(r, has_id=False, target=99.0, x={"c": 50.0}) for r in tr[:50]]
    f2 = X.fit_fold(tr + extra, te, ["c"])
    assert f1["n_fit"] == f2["n_fit"] == len(tr)
    assert f1["b_z"]["c"] == pytest.approx(f2["b_z"]["c"], abs=0.05)
    few = [dict(r, has_id=False) for r in tr]
    f3 = X.fit_fold(few, te, ["c"])
    assert f3["b_u"] == 1.0 and f3["b_z"]["c"] == 0.0


def test_the_reading_rule():
    assert X.reading({"delta": 0.01, "ci95": [0.001, 0.02]}, {"delta": 0.002}) == "CARRY"
    assert X.reading({"delta": 0.01, "ci95": [-0.001, 0.02]}, {"delta": 0.002}) == "LEAN"
    assert X.reading({"delta": 0.01, "ci95": [0.001, 0.02]}, {"delta": -0.002}) == "NULL"
    assert X.reading({"delta": None}, {"delta": 0.1}) == "NULL"


# ---------------------------------------------------------------------------
# 4. bans
# ---------------------------------------------------------------------------

def _frames(fid, fold, year):
    blk = {"train": [{"decision_year": year}], "test": [{"decision_year": fold}]}
    return {fid: {"by_side": {"hit": {fold: blk}}}}


def test_reserved_folds_and_rows_raise():
    X.check_dev_folds(_frames("lv_dev", 2019, 2018))
    X.check_dev_folds(_frames("vm_dev", 2023, 2022))
    for frames in (_frames("lv_dev", 2020, 2018), _frames("lv_dev", 2019, 2021),
                   _frames("vm_dev", 2025, 2022), _frames("vm_dev", 2023, 2025),
                   _frames("lv_res", 2019, 2018)):
        with pytest.raises(F.ReservedFrameError):
            X.check_dev_folds(frames)


_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")
_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def test_no_consensus_level_grouping_no_exporter_no_emdash():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED_TOKENS), name
            assert not fv_group.search(low), name
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & _SERVED_EXPORTERS, mods
    assert chr(0x2014) not in src and chr(0x2013) not in src
    builders = ("column_values", "promotion_values", "rule5_first_year", "trade_principal",
                "load_bonus", "nri_entries", "feed_invitees", "forty_man_on")
    for fn in builders:
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            assert banned not in body.lower(), (fn, banned)


def test_the_fetch_window_and_the_cache_dir():
    def at(h):
        return datetime(2026, 10, 15, h, 30, tzinfo=timezone.utc)
    assert X.fetch_window_open(at(5)) and X.fetch_window_open(at(11))
    assert not X.fetch_window_open(at(6)) and not X.fetch_window_open(at(10))
    assert X.CACHE_DIR.parts[-2:] == (".cache", "efv_x2_revealed")


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def _artifact():
    if not X.OUT_PATH.exists():
        pytest.skip("read not run on this tree")
    return json.loads(X.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_on_the_frozen_label():
    d = _artifact()
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["ships"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["estimator"]["B"] == 2000 and d["estimator"]["seed"] == 20261019
    assert set(d["frames"]) == set(X.FRAMES_DEV)
    assert d["frames"]["lv_dev"]["folds"] == [2017, 2018, 2019]
    assert all(y < F.R_VM_FIRST_DEBUT_YEAR for y in d["frames"]["vm_dev"]["folds"])
    assert d["column_receipts"]["latest_input_date_read"][0] < "2025-01-01"
    names = list(X.COLUMNS) + [X.JOINT]
    assert [s["column"] for s in d["summary"]] == names
    for fid in X.FRAMES_DEV:
        assert set(d["frames"][fid]["liveness_no_column"].values()) == {0.0}
        for n in names:
            blk = d["frames"][fid]["arms"][n]
            for scope in X.SCOPES:
                assert blk[scope]["B"] == 2000 and blk[scope]["seed"] == 20261019
            for k in blk.get("coverage", {}):
                if k == "all":
                    continue
                year = int(k.split("|")[1])
                assert year < F.R_VM_FIRST_DEBUT_YEAR
                assert fid != "lv_dev" or year in X.LV_DEV_FOLDS
    for s in d["summary"]:
        assert s["reading"] in ("CARRY", "LEAN", "NULL")
