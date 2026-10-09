# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""proj_components.build_component_frame (task PJ_2_COMPONENT_FRAME).

Fixture only: a small frozen vintage, a small corpus and in-memory readers.
Nothing here reads data/fwar_vintage.json, the network or a real cache file,
and no frame is cached outside tmp_path. The properties pinned:

  - no lookahead: every lag value is the fixture value of season B-k, every
    label season is B+h-1, and the lag guard raises on a season >= B;
  - the label-season guard raises for 2026 (PJC_LABEL_SEASON_MAX 2025), and
    label season 2020 is excluded;
  - batting + baseRunning + fielding + positional + wLeague + replacement +
    the framing residual equals rar on the frame's rows;
  - Savant (and fielding) files of season >= B are never read for base B;
  - a missing Savant season is a missing flag with no value, never a bare 0;
  - the cache name changes when the schema changes;
  - the live statsapi_saber cache is refused as a label source.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import fwar_vintage
import proj_components as PC
import saber_feed

ROOT = Path(__file__).resolve().parent

CATCHER, HITTER, PITCHER, BENCH, MOPUP = 1001, 1002, 2001, 1003, 2002
SEASONS = range(2010, 2018)
FRAMING = 3.5


def _hit_vals(mid: int, s: int) -> dict:
    parts = {"batting": 10.0 + (s - 2000) / 10.0, "baseRunning": 1.5, "fielding": -2.0,
             "positional": (12.0 if mid == CATCHER else -3.0), "wLeague": 0.7,
             "replacement": 18.0}
    rar = sum(parts.values()) + (FRAMING if mid == CATCHER else 0.0)
    return {**parts, "rar": rar, "war": rar / 10.0, "wSb": 0.4, "ubr": 0.9, "wGdp": 0.2,
            "plateAppearances": None, "numTeams": 1, "woba": 0.330, "wRaa": 5.0,
            "wRc": 70.0, "wRcPlus": 110.0, "spd": 4.5}


def _pit_vals(mid: int, s: int) -> dict:
    return {"war": 2.0 + (s - 2000) / 100.0, "rar": 20.0, "fip": 3.8, "xfip": 3.9,
            "ra9War": 2.5, "gmli": 1.0, "exli": 1.0, "pli": 1.0, "inli": 1.0,
            "eraMinus": 95.0, "fipMinus": 96.0, "md": 0.0, "sd": 0.0, "numTeams": 1}


def _group(fields, rows: dict, ambiguous=None) -> dict:
    return {"status": "frozen", "fields": list(fields), "n_players": len(rows),
            "n_multi_team": 0, "ambiguous_ids": list(ambiguous or []),
            "rows": {str(m): [v[f] for f in fields] for m, v in rows.items()}}


def make_vintage(seasons=SEASONS, ambiguous_in=None) -> dict:
    out = {"schema": fwar_vintage.SCHEMA, "vintage_id": "2026-10-02-fixture0000",
           "seasons": {}}
    for s in seasons:
        hit = {m: _hit_vals(m, s) for m in (CATCHER, HITTER, BENCH)}
        pit = {m: _pit_vals(m, s) for m in (PITCHER, MOPUP)}
        amb = [CATCHER] if ambiguous_in == s else None
        out["seasons"][str(s)] = {
            "hitting": _group(fwar_vintage.HITTING_FIELDS, hit, amb),
            "pitching": _group(fwar_vintage.PITCHING_FIELDS, pit)}
    return out


def make_corpus() -> dict:
    hit, pit = [], []
    for s in SEASONS:
        hit.append({"mlbam": CATCHER, "season": s, "age": s - 1985, "role": "C", "pa": 500.0})
        hit.append({"mlbam": HITTER, "season": s, "age": s - 1990, "role": "H", "pa": 600.0})
        hit.append({"mlbam": BENCH, "season": s, "age": s - 1992, "role": "H", "pa": 90.0})
        pit.append({"mlbam": PITCHER, "season": s, "age": s - 1988, "role": "SP", "ip": 180.0})
        pit.append({"mlbam": MOPUP, "season": s, "age": s - 1989, "role": "RP", "ip": 29.0})
    return {"hit": hit, "pit": pit, "league": {}, "first": 2010, "last": 2017,
            "war_provider": "fwar", "label_shape": "fixture"}


def pa_of(s: int) -> float:
    return 400.0 + (s - 2000)


def ip_of(s: int) -> float:
    return 100.0 + (s - 2000)


class Recorder:
    def __init__(self, missing_sprint=()):
        self.calls: list[tuple] = []
        self.missing_sprint = set(missing_sprint)

    def exposures(self, season, group):
        self.calls.append(("exposures", group, int(season)))
        if group == "hitting":
            return {m: {"pa": pa_of(season), "g": 120.0} for m in (CATCHER, HITTER, BENCH)}
        return {m: {"ip": ip_of(season), "gs": 30.0, "g": 31.0, "bf": 700.0}
                for m in (PITCHER, MOPUP)}

    def fielding(self, season):
        self.calls.append(("fielding", None, int(season)))
        return {CATCHER: {"inn": {"C": 900.0 + season - 2000}, "cframing": FRAMING,
                          "src": "fangraphs"},
                HITTER: {"inn": {"SS": 1100.0, "2B": 50.0}, "cframing": None,
                         "src": "fangraphs"}}

    def savant(self, kind, season):
        self.calls.append(("savant", kind, int(season)))
        if season < PC.SAVANT_FIRST[kind] or (kind == "sprint" and season in self.missing_sprint):
            return None
        return {HITTER: {n: 27.0 + season - 2000 for n in PC.SAVANT_FIELDS[kind]}}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(PC, "CACHE_DIR", tmp_path / "proj_components")
    monkeypatch.setattr(PC, "SRC_CACHE", tmp_path / "src_cache")
    PC.clear_reader_caches()
    yield
    PC.clear_reader_caches()


@pytest.fixture
def rec(monkeypatch):
    r = Recorder(missing_sprint={2015})
    monkeypatch.setattr(PC, "read_exposures", r.exposures)
    monkeypatch.setattr(PC, "read_fielding", r.fielding)
    monkeypatch.setattr(PC, "read_savant", r.savant)
    return r


def _build(first=2013, last=2016, **kw):
    kw.setdefault("use_cache", False)
    kw.setdefault("vintage", make_vintage())
    return PC.build_component_frame(make_corpus(), first, last, **kw)


def _row(frame, side, mid, base):
    return next(r for r in frame[side] if r["mlbam"] == mid and r["base"] == base)


# ---------------------------------------------------------------- no lookahead

def test_every_lag_value_is_season_b_minus_k_and_every_label_is_b_plus_h_minus_1(rec):
    fr = _build()
    assert fr["hit"] and fr["pit"]
    for r in fr["hit"]:
        B = r["base"]
        for k in PC.LAGS:
            assert r["feat"][f"pa_l{k}"] == pa_of(B - k)
            want = _hit_vals(r["mlbam"], B - k)["batting"] / pa_of(B - k)
            assert r["feat"][f"batting_pa_l{k}"] == pytest.approx(want)
        for h, lab in r["labels"].items():
            assert lab["season"] == B + h - 1
            assert lab["pa"] == pa_of(B + h - 1)
            assert lab["batting"] == pytest.approx(_hit_vals(r["mlbam"], B + h - 1)["batting"])
    for r in fr["pit"]:
        B = r["base"]
        for k in PC.LAGS:
            assert r["feat"][f"ip_l{k}"] == ip_of(B - k)
            assert r["feat"][f"war_ip_l{k}"] == pytest.approx(
                _pit_vals(r["mlbam"], B - k)["war"] / ip_of(B - k))
        for h, lab in r["labels"].items():
            assert lab["season"] == B + h - 1
            assert lab["ip"] == ip_of(B + h - 1)


def test_every_lag_read_asks_for_a_season_before_the_base(rec, monkeypatch):
    seen = []
    real = PC._lag

    def spy(season, base):
        seen.append((season, base))
        return real(season, base)

    monkeypatch.setattr(PC, "_lag", spy)
    _build()
    assert seen and all(s <= b - 1 for s, b in seen)
    assert {b - s for s, b in seen} == set(PC.LAGS)


def test_the_lag_guard_raises_on_the_base_season_or_later():
    PC._lag(2014, 2015)
    for s in (2015, 2016):
        with pytest.raises(PC.LookaheadError):
            PC._lag(s, 2015)


@pytest.mark.parametrize("base", [2013, 2014, 2015, 2016])
def test_savant_and_fielding_files_of_season_b_or_later_are_never_read(rec, base):
    _build(base, base)
    lag_reads = [(kind, s) for src, kind, s in rec.calls if src in ("savant", "fielding")]
    assert lag_reads, "the build read no Savant or fielding season"
    assert all(s <= base - 1 for _, s in lag_reads), lag_reads
    assert {s for _, s in lag_reads} == {base - 1, base - 2, base - 3}
    savant_kinds = {kind for kind, _ in lag_reads if kind}
    assert savant_kinds == {"sprint", "oaa", "arm"}


# ---------------------------------------------------------------- label guard

def test_label_season_guard_raises_for_2026(rec):
    assert PC.PJC_LABEL_SEASON_MAX == 2025
    with pytest.raises(PC.PJCLabelSeasonError):
        PC.check_label_season(2026)
    with pytest.raises(PC.PJCLabelSeasonError):
        PC.build_component_frame(make_corpus(), 2014, 2026, use_cache=False,
                                 vintage=make_vintage(range(2010, 2027)))
    assert rec.calls == [], "the guard fires before anything is read"
    assert PC.check_label_season(2025) == 2025


def test_label_season_2020_is_excluded():
    assert PC.PJC_EXCLUDED_LABEL_SEASONS == {2020}
    assert PC.label_seasons(2018, 2025) == {1: 2018, 2: 2019, 4: 2021, 5: 2022}
    assert PC.label_seasons(2024, 2025) == {1: 2024, 2: 2025}


def test_the_live_saber_cache_is_refused_as_a_label_source(rec):
    for bad in (Path(".cache") / "statsapi_saber_hitting_2025.json",
                ".cache/statsapi_saber_pitching_2024.json"):
        with pytest.raises(PC.LiveLabelRefused):
            _build(vintage=bad)
    with pytest.raises(PC.LiveLabelRefused):
        _build(vintage={"stats": [{"splits": []}]})
    with pytest.raises(PC.LiveLabelRefused):
        _build(vintage=[1, 2])


def test_a_label_season_the_vintage_does_not_hold_frozen_raises(rec):
    with pytest.raises(PC.VintageShapeError):
        _build(2013, 2016, vintage=make_vintage(range(2010, 2016)))


# ---------------------------------------------------------------- identity

def test_run_parts_plus_framing_residual_equal_rar(rec):
    fr = _build()
    n = 0
    for r in fr["hit"]:
        for lab in r["labels"].values():
            tot = sum(lab[p] for p in saber_feed.RUN_PARTS) + lab["framing"]
            assert tot == pytest.approx(lab["rar"], abs=1e-9)
            n += 1
        for k in PC.LAGS:
            tot = sum(r["feat"][f"{p}_pa_l{k}"] for p in saber_feed.RUN_PARTS)
            tot += r["feat"][f"framing_pa_l{k}"]
            assert tot == pytest.approx(r["feat"][f"rar_pa_l{k}"], abs=1e-12)
    assert n > 0
    cat = _row(fr, "hit", CATCHER, 2015)
    assert cat["labels"][1]["framing"] == pytest.approx(FRAMING)
    assert _row(fr, "hit", HITTER, 2015)["labels"][1]["framing"] == pytest.approx(0.0)
    assert cat["feat"]["cframing_l1"] == FRAMING
    assert cat["feat"]["inn_C_l1"] == 900.0 + 14


def test_framing_is_saber_feed_framing_residual():
    row = _hit_vals(CATCHER, 2015)
    assert PC._hit_parts(row)["framing"] == saber_feed.framing_residual(row)


# ---------------------------------------------------------------- missing flags

def test_a_missing_savant_season_is_a_flag_not_a_zero(rec):
    fr = _build(2013, 2017)
    r = _row(fr, "hit", HITTER, 2017)            # the 2015 sprint file is missing in the fixture
    assert r["feat"]["sprint_speed_l1"] == 27.0 + 16
    assert r["feat"]["sprint_missing_l1"] == 0
    assert r["feat"]["sprint_speed_l2"] is None
    assert r["feat"]["sprint_missing_l2"] == 1
    assert r["feat"]["oaa_l1"] == 27.0 + 16 and r["feat"]["oaa_missing_l1"] == 0
    assert r["feat"]["oaa_l2"] is None and r["feat"]["oaa_missing_l2"] == 1  # before 2016
    assert r["feat"]["arm_overall_l1"] is None and r["feat"]["arm_missing_l1"] == 1  # before 2020
    other = _row(fr, "hit", CATCHER, 2016)       # not on any Savant board
    for kind in ("sprint", "oaa", "arm"):
        for k in PC.LAGS:
            assert other["feat"][f"{kind}_missing_l{k}"] == 1
            for name in PC.SAVANT_FIELDS[kind]:
                assert other["feat"][f"{name}_l{k}"] is None


def test_the_default_savant_reader_returns_none_for_an_absent_or_early_season(tmp_path):
    d = PC.SRC_CACHE / "savant_sprint"
    d.mkdir(parents=True)
    (d / "sprint_2016.csv").write_text(
        '"last_name, first_name","player_id","team_id","team","position","age",'
        '"competitive_runs","bolts","hp_to_1b","sprint_speed"\n'
        '"Doe, Jo",1002,1,"AAA","SS",25,"30","5","4.1","28.4"\n', encoding="utf-8")
    assert PC.read_savant("sprint", 2016) == {HITTER: {"sprint_speed": 28.4}}
    assert PC.read_savant("sprint", 2017) is None      # file absent
    assert PC.read_savant("sprint", 2014) is None      # before the source
    assert PC.read_savant("arm", 2019) is None
    assert PC.read_savant("oaa", 2016) is None


def test_the_default_oaa_reader_sums_positions(tmp_path):
    d = PC.SRC_CACHE / "savant_oaa"
    d.mkdir(parents=True)
    head = ('"last_name, first_name","player_id","display_team_name","year",'
            '"primary_pos_formatted","fielding_runs_prevented","outs_above_average"\n')
    (d / "oaa_2018_pos6.csv").write_text(head + '"Doe, Jo","1002","X","2018","SS","4",5\n',
                                         encoding="utf-8")
    (d / "oaa_2018_pos4.csv").write_text(head + '"Doe, Jo","1002","X","2018","SS","-1",-2\n',
                                         encoding="utf-8")
    assert PC.read_savant("oaa", 2018) == {HITTER: {"oaa": 3.0, "frp": 3.0}}


def test_the_default_fielding_reader_uses_fangraphs_then_statsapi_before_2011():
    fg = PC.SRC_CACHE / "fangraphs"
    fg.mkdir(parents=True)
    rows = [{"xMLBAMID": CATCHER, "Pos": "C", "Inn": 800.2, "CFraming": 2.5},
            {"xMLBAMID": CATCHER, "Pos": "1B", "Inn": 10.1, "CFraming": None},
            {"xMLBAMID": PITCHER, "Pos": "P", "Inn": 180.0, "CFraming": None}]
    (fg / "fielding_2012.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    got = PC.read_fielding(2012)
    assert set(got) == {CATCHER}
    assert got[CATCHER]["inn"]["C"] == pytest.approx(800 + 2 / 3)
    assert got[CATCHER]["inn"]["1B"] == pytest.approx(10 + 1 / 3)
    assert got[CATCHER]["cframing"] == 2.5 and got[CATCHER]["src"] == "fangraphs"
    sa = PC.SRC_CACHE / "statsapi_field"
    sa.mkdir(parents=True)
    doc = {"stats": [{"splits": [{"player": {"id": HITTER}, "position": {"abbreviation": "SS"},
                                  "stat": {"games": 100, "gamesStarted": 98, "innings": "850.1"}}]}]}
    (sa / "fld_2010.json").write_text(json.dumps(doc), encoding="utf-8")
    old = PC.read_fielding(2010)
    assert old[HITTER]["src"] == "statsapi" and old[HITTER]["inn"]["SS"] == pytest.approx(850.3)
    assert PC.read_fielding(2009) is None


def test_a_missing_fielding_season_is_flagged_not_zeroed(rec, monkeypatch):
    monkeypatch.setattr(PC, "read_fielding", lambda s: None)
    r = _row(_build(), "hit", HITTER, 2015)
    assert r["feat"]["fld_missing_l1"] == 1
    assert r["feat"]["inn_SS_l1"] is None and r["feat"]["inn_total_l1"] is None


# ---------------------------------------------------------------- universe, exposures

def test_the_veteran_universe_matches_proj_export():
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    assert re.search(r"^MIN_PA, MIN_IP = 100, 30$", src, re.M)
    assert (PC.MIN_PA, PC.MIN_IP) == (100, 30)


def test_rows_cover_the_veteran_universe_only(rec):
    fr = _build()
    assert {r["mlbam"] for r in fr["hit"]} == {CATCHER, HITTER}
    assert {r["mlbam"] for r in fr["pit"]} == {PITCHER}
    assert sorted({r["base"] for r in fr["hit"]}) == [2013, 2014, 2015, 2016]
    assert _row(fr, "hit", HITTER, 2015)["age"] == 2015 - 1990
    assert set(_row(fr, "hit", HITTER, 2013)["feat"]) == set(PC.feature_names("hit"))
    assert set(_row(fr, "pit", PITCHER, 2013)["feat"]) == set(PC.feature_names("pit"))
    assert set(_row(fr, "pit", PITCHER, 2013)["labels"][1]) == set(PC.label_names("pit"))
    counts = PC.row_counts(fr)
    assert counts["hit"]["rows"] == 8 and counts["hit"]["bases"] == [2013, 2016]
    assert counts["hit"]["labelled_by_h"] == {1: 8, 2: 6, 3: 4, 4: 2, 5: 0}


def test_pitcher_exposures_come_from_the_raw_cache_never_the_vintage():
    assert "inningsPitched" not in fwar_vintage.PITCHING_FIELDS
    assert not {"ip", "gs", "g"} & set(PC.PIT_VINTAGE_FIELDS)


def test_raw_exposures_resolve_a_repeated_id_and_count_it():
    def sp(pid, n, ip, gs=1, g=2, tot=None):
        d = {"player": {"id": pid}, "stat": {"inningsPitched": ip, "gamesStarted": gs,
                                            "gamesPlayed": g, "battersFaced": 10}}
        if tot is not None:
            d["numTeams"] = tot
        return d
    splits = [sp(1, 1, "10.1"), sp(1, 1, "5.2"), sp(1, 2, "16.0", tot=2),
              sp(2, 1, "3.1"), sp(2, 1, "1.1"), sp(3, 1, "190.2")]
    out, receipt = PC.exposures_from_splits(splits, "pitching")
    assert out[1]["ip"] == pytest.approx(16.0)          # resolved to the season total
    assert out[2]["ip"] == pytest.approx(4 + 2 / 3)     # no total row: summed (D1)
    assert out[3]["ip"] == pytest.approx(190 + 2 / 3)
    assert receipt == {"n_rows": 6, "n_repeated_ids": 2, "n_resolved_to_total": 1,
                       "n_summed": 1}


def test_a_vintage_season_that_is_not_one_row_per_player_raises(rec):
    with pytest.raises(PC.VintageShapeError):
        _build(vintage=make_vintage(ambiguous_in=2014))


@pytest.mark.parametrize("raw,want", [("190.1", 190 + 1 / 3), ("12.2", 12 + 2 / 3),
                                      (1043.2, 1043 + 2 / 3), ("7.0", 7.0), (None, 0.0)])
def test_innings_read_baseball_thirds(raw, want):
    assert PC.innings(raw) == pytest.approx(want)


# ---------------------------------------------------------------- cache

def test_the_cache_name_changes_when_the_schema_changes(monkeypatch):
    corpus = make_corpus()
    p0 = PC.cache_path(2014, 2025, "vid", corpus)
    assert p0.parent == PC.CACHE_DIR
    assert re.fullmatch(r"frame_[0-9a-f]{10}_vid_2014_2025\.pkl", p0.name)
    parts, version = PC.HIT_PARTS, PC.FRAME_VERSION
    monkeypatch.setattr(PC, "HIT_PARTS", parts + ("extra",))
    p1 = PC.cache_path(2014, 2025, "vid", corpus)
    monkeypatch.setattr(PC, "HIT_PARTS", parts)
    assert PC.cache_path(2014, 2025, "vid", corpus) == p0
    monkeypatch.setattr(PC, "FRAME_VERSION", version + 1)
    p2 = PC.cache_path(2014, 2025, "vid", corpus)
    monkeypatch.setattr(PC, "FRAME_VERSION", version)
    assert len({p0, p1, p2}) == 3
    assert PC.cache_path(2014, 2025, "vid", {**corpus, "war_provider": "bwar"}) != p0
    assert PC.cache_path(2014, 2025, "other", corpus) != p0


def test_the_frame_round_trips_through_its_cache(rec, monkeypatch):
    fr = _build(use_cache=True)
    path = PC.cache_path(2013, 2016, "2026-10-02-fixture0000", make_corpus())
    assert path.exists() and fr["meta"]["schema_tag"] in path.name

    def boom(*a, **k):
        raise AssertionError("a cached frame must not re-read its sources")

    for name in ("read_exposures", "read_fielding", "read_savant"):
        monkeypatch.setattr(PC, name, boom)
    again = _build(use_cache=True)
    assert again["meta"] == fr["meta"] and len(again["hit"]) == len(fr["hit"])
    assert fr["meta"]["vintage_id"] == "2026-10-02-fixture0000"
    assert fr["meta"]["n_rows"] == {"hit": 8, "pit": 4}


# ============================================================================
# The heads (task PJ_4_COMPONENT_HEADS_DEV): project_components and the DEV
# contract. Fixtures only: a corpus with rate stats so the engine projects,
# empty aging curves, hand-made held constants, the Recorder frame above.
# ============================================================================

import fa_projection as fp
import fwar_frame as F

HEADS_SEASONS = range(2010, 2016)
HEADS_BASE = 2015


def make_heads_corpus() -> dict:
    hit, pit, league = [], [], {}
    for s in HEADS_SEASONS:
        hit.append({"mlbam": CATCHER, "season": s, "age": s - 1985, "role": "C", "pa": 500.0,
                    "k_pct": 0.22, "bb_pct": 0.07, "iso": 0.14, "babip": 0.29, "hr_pa": 0.025,
                    "woba": 0.320, "war": 2.0, "war_total": 2.0})
        hit.append({"mlbam": HITTER, "season": s, "age": s - 1990, "role": "H", "pa": 600.0,
                    "k_pct": 0.18, "bb_pct": 0.10, "iso": 0.20, "babip": 0.31, "hr_pa": 0.04,
                    "woba": 0.360, "war": 4.0, "war_total": 4.0})
        hit.append({"mlbam": BENCH, "season": s, "age": s - 1992, "role": "H", "pa": 90.0,
                    "k_pct": 0.25, "bb_pct": 0.06, "iso": 0.10, "babip": 0.28, "hr_pa": 0.01,
                    "woba": 0.290, "war": 0.1, "war_total": 0.1})
        pit.append({"mlbam": PITCHER, "season": s, "age": s - 1988, "role": "SP", "bf": 760.0,
                    "ip": 180.0, "k_pct": 0.23, "bb_pct": 0.07, "hr_bf": 0.028, "fip": 3.6,
                    "war": 3.5, "war_total": 3.5})
        pit.append({"mlbam": MOPUP, "season": s, "age": s - 1989, "role": "RP", "bf": 125.0,
                    "ip": 29.0, "k_pct": 0.20, "bb_pct": 0.09, "hr_bf": 0.03, "fip": 4.4,
                    "war": 0.1, "war_total": 0.1})
        league[s] = {"season": s, "_total_pa": 180000.0, "woba": 0.315, "r_pa": 0.12,
                     "k_pct": 0.20, "bb_pct": 0.08, "iso": 0.15, "babip": 0.30, "hr_pa": 0.03,
                     "fip_constant": 3.1, "era": 4.0, "p_k_pct": 0.20, "p_bb_pct": 0.08,
                     "p_hr_bf": 0.03, "lg_fip": 4.0}
    return {"hit": hit, "pit": pit, "league": league, "first": 2010, "last": 2015,
            "war_provider": "fwar", "label_shape": "fixture"}


def heads_curves() -> dict:
    """Empty component curves plus a 'pt' curve and a K% curve on the hitter
    base role, so the walks move and the profile role falls back to it."""
    pt = {str(a): {"delta": -15.0 * (a - 29), "delta_smooth": -12.0 * (a - 29)} for a in range(25, 40)}
    k = {str(a): {"delta": 0.004, "delta_smooth": 0.003} for a in range(25, 40)}
    return {"hit": {"H": {"pt": pt, "k_pct": k}, "C": {"pt": pt}},
            "pit": {"SP": {"pt": pt}, "RP": {"pt": pt}}, "meta": {}}


HEADS_CONSTS = {"season": 2014, "lg_r_pa": 0.12, "lg_ra9": 4.5, "lg_era": 4.2, "rpw": 10.0,
                "fip_constant": 3.1, "lg_pa": 180000.0, "woba_scale": 1.2, "eng_lg_woba": 0.315,
                "lg_nonp_wrc_pa": 0.1236, "lg_adj_rate": 0.0025, "rep_per_pa": 0.03,
                "lg_fipr9": 4.5, "mlb_games": 2430.0, "inn_per_pa": 2.14, "pf": 1.0,
                "warip": -0.0004, "lg_woba_feed": 0.313}

HEADS_PARAMS = {"shrink": {"bsr_pa": 600, "fld_inn": 2000, "gmli_g": 40, "ra9gap_ip": 400},
                "savant": {}, "R_relief": 3.7, "ranges": {}}


class _NeverRead:
    """A war_map stand-in that raises on any read: the heads never touch it."""

    def __getattr__(self, name):
        raise AssertionError(f"war_map read ({name})")

    def __getitem__(self, key):
        raise AssertionError(f"war_map read ({key!r})")

    def get(self, *a, **k):
        raise AssertionError("war_map read (get)")


def _hist(corpus, side, mlbam, base):
    rows = {r["season"]: r for r in corpus[side] if r["mlbam"] == mlbam}
    return [rows[s] for s in (base - 1, base - 2, base - 3) if s in rows]


def _heads_inputs(rec, mlbam_hit=HITTER, mlbam_pit=PITCHER, base=HEADS_BASE):
    fr = _build(2013, 2015)
    feat = {}
    if mlbam_hit is not None:
        feat["hit"] = _row(fr, "hit", mlbam_hit, base)["feat"]
    if mlbam_pit is not None:
        feat["pit"] = _row(fr, "pit", mlbam_pit, base)["feat"]
    return feat


def _project(rec, mlbam_hit=HITTER, mlbam_pit=PITCHER, params=HEADS_PARAMS, feat=None,
             war_map=None, age=None):
    corpus = make_heads_corpus()
    feat = feat if feat is not None else _heads_inputs(rec, mlbam_hit, mlbam_pit)
    hist = {}
    if mlbam_hit is not None:
        hist["hit"] = _hist(corpus, "hit", mlbam_hit, HEADS_BASE)
    if mlbam_pit is not None:
        hist["pit"] = _hist(corpus, "pit", mlbam_pit, HEADS_BASE)
    any_hist = next(iter(hist.values()))
    age = age if age is not None else any_hist[0]["age"] + 1
    return PC.project_components(hist, HEADS_BASE, age, heads_curves(),
                                 _NeverRead() if war_map is None else war_map,
                                 corpus["league"], HEADS_CONSTS, feat, params), corpus


def test_the_grids_are_the_registered_four_point_grids():
    assert PC.K_GRIDS == {"bsr_pa": (300, 600, 1200, 2400), "fld_inn": (1000, 2000, 4000, 8000),
                          "gmli_g": (20, 40, 80, 160), "ra9gap_ip": (200, 400, 800, 1600)}
    assert set(PC.SAVANT_TERMS) == {"sprint", "oaa", "arm"}
    assert PC.SAVANT_TERMS["sprint"][0] == "bsr"
    assert {PC.SAVANT_TERMS[t][0] for t in ("oaa", "arm")} == {"fld"}


def test_identity_components_summed_over_rpw_equal_h8(rec):
    out, _ = _project(rec)
    blk = out["hit"]
    assert blk is not None and blk["not_projected"] == []
    for h in range(1, PC.HORIZONS + 1):
        ln = blk["lines"][h]
        tot = ln["bat"] + ln["bsr"] + ln["fld"] + ln["pos"] + ln["lg"] + ln["rep"]
        assert ln["war_comp"] == pytest.approx(tot / HEADS_CONSTS["rpw"], abs=1e-9)
        assert ln["fld_pos"] == pytest.approx(ln["fld"] + ln["pos"], abs=1e-12)
        # the held constants, PF 1.0: no park term, league and replacement
        # proportional to PA
        assert ln["lg"] == pytest.approx(HEADS_CONSTS["lg_adj_rate"] * ln["pa"])
        assert ln["rep"] == pytest.approx(HEADS_CONSTS["rep_per_pa"] * ln["pa"])
        assert F.park_runs(ln["pa"], HEADS_CONSTS["lg_r_pa"], 1.0) == 0.0


def test_h1_woba_path_equals_rate_path(rec):
    out, corpus = _project(rec)
    hist = _hist(corpus, "hit", HITTER, HEADS_BASE)
    age = hist[0]["age"] + 1
    proj = fp.project_player(hist, "hit", HEADS_BASE, heads_curves(), corpus["league"], age)
    path = fp.rate_path(proj, "hit", heads_curves(), corpus["league"], PC.HORIZONS)
    assert len(path) == PC.HORIZONS
    for t, p in enumerate(path):
        assert out["hit"]["lines"][t + 1]["woba"] == pytest.approx(p["woba"], abs=1e-9)
    # the K% curve moves the walk, so the path is not flat
    assert len({round(p["woba"], 6) for p in path}) > 1
    # year 1 carries the engine's own rates and exposure
    assert out["hit"]["lines"][1]["k_pct"] == proj["k_pct"]
    assert out["hit"]["lines"][1]["pa"] == proj["pt_proj"]
    # and the batting runs are fwar_frame.wraa plus the league term on that wOBA
    ln = out["hit"]["lines"][1]
    want = (F.wraa(p0 := path[0]["woba"], HEADS_CONSTS["eng_lg_woba"], HEADS_CONSTS["woba_scale"], ln["pa"])
            + F.league_batting_runs(ln["pa"], HEADS_CONSTS["lg_r_pa"], HEADS_CONSTS["lg_nonp_wrc_pa"]))
    assert ln["bat"] == pytest.approx(want, abs=1e-9)
    assert p0 == path[0]["woba"]


def test_the_exposure_walk_is_the_champion_pt_walk_floored_at_zero(rec):
    out, corpus = _project(rec)
    hist = _hist(corpus, "hit", HITTER, HEADS_BASE)
    age = hist[0]["age"] + 1
    curves = heads_curves()
    proj = fp.project_player(hist, "hit", HEADS_BASE, curves, corpus["league"], age)
    role = fp.profile_role(hist, "hit", proj["role"], corpus["league"])
    e, a, want = proj["pt_proj"], age, [proj["pt_proj"]]
    for _t in range(1, PC.HORIZONS):
        a += 1
        e = max(0.0, e + fp.curve_delta(curves, "hit", role, "pt", a))
        want.append(e)
    got = [out["hit"]["lines"][h]["pa"] for h in range(1, PC.HORIZONS + 1)]
    assert got == pytest.approx(want)
    assert len(set(got)) > 1
    # a steep decline floors at zero rather than going negative
    steep = {"hit": {"H": {"pt": {str(x): {"delta": -400.0} for x in range(20, 45)}}}, "pit": {}}
    walk = PC.exposure_walk(500.0, "hit", "H", 30, steep)
    assert walk[0] == 500.0 and walk[-1] == 0.0 and min(walk) == 0.0


def test_pitcher_chain_is_fwar_frame_at_pf_1_with_no_framing_charge(rec):
    out, corpus = _project(rec)
    blk = out["pit"]
    assert blk is not None and blk["role"] == "SP"
    c = HEADS_CONSTS
    for h in range(1, PC.HORIZONS + 1):
        ln = blk["lines"][h]
        assert ln["ip"] == pytest.approx(ln["bf"] / PC.BF_PER_IP)
        pfr = F.pfipr9(F.fipr9(ln["fip"], c["lg_ra9"], c["lg_era"]), 1.0)
        line = F.blended_line(ln["ip"], ln["g"], ln["gs"], c["lg_fipr9"], c["lg_fipr9"], pfr, ln["gmli"])
        war, _rar = F.pitcher_war([line], c["warip"])
        assert ln["war_fip"] == pytest.approx(war, abs=1e-9)
        assert ln["raap9"] == pytest.approx(F.raap9(c["lg_fipr9"], pfr))
        assert ln["fip_runs_100ip"] == pytest.approx(ln["raap9"] * 100.0 / 9.0)
        assert ln["war_ra9"] == pytest.approx(ln["war_fip"] + ln["ra9gap_100ip"] * ln["ip"] / 100.0)
    # P2 is rate_path's FIP path
    hist = _hist(corpus, "pit", PITCHER, HEADS_BASE)
    proj = fp.project_player(hist, "pit", HEADS_BASE, heads_curves(), corpus["league"], hist[0]["age"] + 1)
    path = fp.rate_path(proj, "pit", heads_curves(), corpus["league"], PC.HORIZONS)
    assert [blk["lines"][h]["fip"] for h in range(1, 6)] == [p["fip"] for p in path]


def test_no_function_returns_a_war_label_prediction_outside_h8_and_p3(rec):
    out, _ = _project(rec)                      # war_map is _NeverRead: never touched
    hit_keys = {k for ln in out["hit"]["lines"].values() for k in ln if "war" in k.lower()}
    pit_keys = {k for ln in out["pit"]["lines"].values() for k in ln if "war" in k.lower()}
    assert hit_keys == {"war_comp"}             # H8 only
    assert pit_keys == {"war_fip", "war_ra9"}   # P3, and P5 beside it
    assert "war" not in {k.lower() for k in PC.HIT_LINE_KEYS} | {k.lower() for k in PC.PIT_LINE_KEYS}
    # the comparators and the scorer rows carry no WAR quantity at all
    fr = _build(2013, 2015)
    for side in ("hit", "pit"):
        for r in fr[side]:
            naive = PC.naive_components(side, r["feat"])
            assert not any("war" in k.lower() for k in naive)
            rows = PC.scorer_rows(r, side, [(r["base"], h) for h in range(1, 6)],
                                  {s: HEADS_CONSTS for s in range(2010, 2020)}, 3.7)
            for row in rows:
                assert not any(str(k).lower() == "war" for k in row["labels"])
                assert row["label_season"] == row["base"] + row["h"] - 1
    # a scorer row with a war key is refused by the scorer itself
    import proj_eval as pe
    with pytest.raises(ValueError):
        pe.run_components([{"mlbam": 1, "side": "hit", "base": 2015, "h": 1, "exposure": 500.0,
                            "labels": {"bsr": 1.0}}],
                          {"bsr": lambda r: {"rate": 1.0, "war": 2.0}},
                          {"bsr": {"naive": lambda r: 0.0}}, [(2015, 1)], 1, B=5)


def test_a_component_with_no_history_is_none_and_reported_not_projected(rec):
    feat = _heads_inputs(rec)
    hit = dict(feat["hit"])
    for k in PC.LAGS:
        hit[f"baseRunning_pa_l{k}"] = None          # no baserunning history
        hit[f"fld_missing_l{k}"] = 1                 # no fielding innings on any lag
        hit[f"inn_total_l{k}"] = None
    pit = dict(feat["pit"])
    for k in PC.LAGS:
        pit[f"ra9gap_100ip_l{k}"] = None
    out, _ = _project(rec, feat={"hit": hit, "pit": pit})
    blk = out["hit"]
    assert blk["not_projected"] == ["bsr", "fld", "pos"]
    for ln in blk["lines"].values():
        assert ln["bsr"] is None and ln["fld"] is None and ln["pos"] is None
        assert ln["fld_pos"] is None and ln["war_comp"] is None
        assert ln["bat"] is not None and ln["lg"] is not None      # the rest still projects
    assert out["pit"]["not_projected"] == ["ra9_gap"]
    for ln in out["pit"]["lines"].values():
        assert ln["ra9gap_100ip"] is None and ln["war_ra9"] is None
        assert ln["war_fip"] is not None
    # a reliever with no gmLI history: P3 prices at the neutral multiplier and says so
    out2, _ = _project(rec, mlbam_hit=None, mlbam_pit=PITCHER, feat={"pit": dict(
        pit, **{f"gmli_l{k}": None for k in PC.LAGS}, **{f"gs_share_l{k}": 0.0 for k in PC.LAGS},
        **{f"gs_l{k}": 0.0 for k in PC.LAGS})})
    assert out2["hit"] is None
    assert "gmli" in out2["pit"]["not_projected"] or out2["pit"]["role"] == "SP"
    assert out2["pit"]["lines"][1]["gmli"] is None
    # a component that is None never gets a range or a rate
    fixed = dict(HEADS_PARAMS, ranges={"bsr": {"1": {"hit:hi": {"q10": -1.0, "q90": 1.0, "n": 99}}}})
    out3, _ = _project(rec, feat={"hit": hit, "pit": pit}, params=fixed)
    assert "bsr" not in out3["hit"]["lines"][1]["ranges"]


def test_two_way_rows_carry_both_sides_and_a_missing_side_is_none(rec):
    out, _ = _project(rec)
    assert out["two_way"] is True and out["hit"] is not None and out["pit"] is not None
    only_hit, _ = _project(rec, mlbam_pit=None)
    assert only_hit["two_way"] is False and only_hit["pit"] is None
    only_pit, _ = _project(rec, mlbam_hit=None)
    assert only_pit["two_way"] is False and only_pit["hit"] is None


def test_marcel_rate_is_the_def_rate_form_and_naive_is_5_4_3():
    items = [(1, 2.0, 600.0), (2, -1.0, 300.0), (3, 4.0, 100.0)]
    w = fp._marcel_weights()                     # 5/3/2
    num = 600 * 2.0 + (w[1] / w[0]) * 300 * -1.0 + (w[2] / w[0]) * 100 * 4.0
    den = 600 + (w[1] / w[0]) * 300 + (w[2] / w[0]) * 100
    rate, got_den = PC.marcel_rate(items, 600.0)
    assert got_den == pytest.approx(den)
    assert rate == pytest.approx(num / den * den / (den + 600.0))
    shrunk_to_one, _ = PC.marcel_rate([(1, 1.4, 20.0)], 20.0, target=1.0)
    assert shrunk_to_one == pytest.approx(1.2)
    assert PC.marcel_rate([(1, None, 10.0), (2, 1.0, 0.0)], 100.0) == (None, 0.0)
    naive = PC.naive_rate(items)
    assert naive == pytest.approx((5 * 600 * 2.0 + 4 * 300 * -1.0 + 3 * 100 * 4.0) / (5 * 600 + 4 * 300 + 3 * 100))
    assert PC.naive_rate([(1, None, 5.0)]) is None


def test_the_age_walk_is_cumulative_nearest_age_and_zero_without_a_curve():
    curve = {28: {"delta": 1.0, "delta_smooth": 0.5}, 29: {"delta": -1.0, "delta_smooth": -0.25}}
    assert PC.age_walk(curve, 28, 3) == pytest.approx([0.5, 0.25, 0.0])
    assert PC.age_walk(None, 28, 3) == [0.0, 0.0, 0.0]
    assert PC.age_walk({"30": {"delta": 2.0}}, 25, 2) == pytest.approx([2.0, 4.0])


def test_params_hash_is_independent_of_formatting():
    a = {"shrink": {"bsr_pa": 300}, "x": [1, 2]}
    b = json.loads('{\n "x": [1, 2],\n "shrink": {"bsr_pa": 300}\n}')
    assert PC.params_hash(a) == PC.params_hash(b)
    PC.check_params(a, PC.params_hash(a).upper())
    with pytest.raises(PC.ParamsHashMismatch):
        PC.check_params(a, "0" * 64)
