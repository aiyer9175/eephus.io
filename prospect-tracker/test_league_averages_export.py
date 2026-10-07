# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The League Averages exporter's contract (league_averages.py; plan Part 8
item P8.2, task LT-04; the lane design's section 10).

The artifacts pinned here are mlb_league_panel_*.json (one panel per season)
and mlb_league_series.json (the over-time series). While
MLBSTATS_LEAGUE_TEAMS_LIVE is False they are written only under
.cache/league_teams/preview/; nothing here writes under data/.

What is pinned:
  * every pooled group equals a direct recompute from the panel's own rows,
    with formulas typed here independently of the module;
  * the FIP constant equals league_constants.league_totals within 0.0005 on
    every completed season;
  * league PA equals batters faced and pitches seen equal pitches thrown on
    every completed season in the cache;
  * a completed season's all group reproduces the window lab's recipe through
    mlbstats_rates;
  * no group, cell or filter key names a scouting grade (fv, efv, grade);
  * no vs-hand group exists (the hand filters are the player's own side);
  * sp_ip_per_gs (starts only) sits beside ip_per_gs in the series for every
    season;
  * the refusals keep the last good file.

The real-cache tests read the gitignored season caches and skip when they are
absent; nothing here makes a network request.
"""
from __future__ import annotations

import json
import re
import socket
from datetime import date
from pathlib import Path

import pytest

import league_averages as L

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
PANEL_ARTIFACT = "mlb_league_panel_*.json"
SERIES_ARTIFACT = "mlb_league_series.json"


def _have(season: int) -> bool:
    return ((CACHE / f"fa_statsapi_hitting_{season}.json").exists()
            and (CACHE / f"fa_statsapi_pitching_{season}.json").exists())


needs_cache = pytest.mark.skipif(not _have(2025), reason="season caches absent")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("league_averages must not open a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture(scope="module")
def panels():
    if not _have(2025):
        pytest.skip("season caches absent")
    live = L.live_season_of()
    out = {}
    for y in sorted({2000, 2020, 2021, 2023, 2025, live}):
        if _have(y):
            out[y] = L.build_panel(y, live_season=live)
    return out


def _rows(doc: dict, side: str) -> list:
    cols = doc[side]["cols"]
    return [dict(zip(cols, r)) for r in doc[side]["rows"]]


# --------------------------------------------------------------------------- #
# an independent group selector and independent formulas
# --------------------------------------------------------------------------- #
BANDS = {"age_24u": (0, 24), "age_25_27": (25, 27), "age_28_30": (28, 30),
         "age_31_33": (31, 33), "age_34o": (34, 200)}


def _select(side: str, key: str, rows: list) -> list:
    base = ([r for r in rows if r["pos"] != "P"] if side == "hit"
            else [r for r in rows if r["pos"] == "P"])
    if key == "all":
        return [r for r in rows if r["pos"] != "P"] if side == "hit" else list(rows)
    if key in ("all_incl_p",):
        return list(rows)
    if key == "pitchers_only":
        return base
    kind, _, val = key.partition("_")
    if kind == "pos":
        named = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
        return [r for r in base if (r["pos"] == val if val != "other" else r["pos"] not in named)]
    if kind in ("bats", "throws"):
        return [r for r in base if r[kind] == val]
    if kind == "role":
        return [r for r in base if r["role"] == val]
    if kind == "lg":
        return [r for r in base if r["lg"] == val]
    if key in BANDS:
        lo, hi = BANDS[key]
        return [r for r in base if r["age"] is not None and lo <= r["age"] <= hi]
    if key == "sample_floor":
        return [r for r in base if (r["pa"] >= 100 if side == "hit" else r["outs"] >= 60)]
    if key == "sample_board":
        return [r for r in base if r["bq"]]
    if key == "sample_title":
        return [r for r in base if r["tq"]]
    raise AssertionError(f"unknown group {side}/{key}")


def _s(rows, col):
    return sum(r[col] or 0 for r in rows)


def _close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def _hit_direct(rows):
    pa, ab, h = _s(rows, "pa"), _s(rows, "ab"), _s(rows, "h")
    d, t, hr = _s(rows, "d"), _s(rows, "t"), _s(rows, "hr")
    bb, hbp, sf, so = _s(rows, "bb"), _s(rows, "hbp"), _s(rows, "sf"), _s(rows, "so")
    sb, cs = _s(rows, "sb"), _s(rows, "cs")
    tb = (h - d - t - hr) + 2 * d + 3 * t + 4 * hr
    out = {}
    if ab:
        out.update(avg=h / ab, slg=tb / ab, iso=(tb - h) / ab)
    if ab + bb + hbp + sf:
        out["obp"] = (h + bb + hbp) / (ab + bb + hbp + sf)
    if pa:
        out.update(k_pct=so / pa, bb_pct=bb / pa, hr_pct=hr / pa)
    pr = [r for r in rows if r["pit"] is not None]
    if _s(pr, "pa"):
        out["p_per_pa"] = _s(pr, "pit") / _s(pr, "pa")
    if sb + cs:
        out["sb_pct"] = sb / (sb + cs)
    wr = [r for r in rows if r["hem"] is not None and r["pa"]]
    if wr:
        out["hem"] = sum(r["hem"] * r["pa"] for r in wr) / _s(wr, "pa")
    return out


def _pit_direct(rows, fip_c):
    outs = _s(rows, "outs")
    out = {}
    if outs:
        ip = outs / 3.0
        out["era"] = 9 * _s(rows, "er") / ip
        out["whip"] = (_s(rows, "h") + _s(rows, "bb")) / ip
        out["fip"] = ((13 * _s(rows, "hr") + 3 * (_s(rows, "bb") + _s(rows, "hbp"))
                       - 2 * _s(rows, "so")) / ip + fip_c)
    bf = _s(rows, "bf")
    if bf:
        out["k_pct"] = _s(rows, "so") / bf
        out["bb_pct"] = _s(rows, "bb") / bf
    pr = [r for r in rows if r["pit"] is not None]
    if _s(pr, "outs"):
        out["p_per_ip"] = _s(pr, "pit") / (_s(pr, "outs") / 3.0)
    if _s(pr, "bf"):
        out["p_per_bf"] = _s(pr, "pit") / _s(pr, "bf")
    sem = [r for r in rows if r["plus_board"] == "sem" and r["outs"]]
    if sem:
        out["sem"] = sum(r["plus"] * r["outs"] for r in sem) / _s(sem, "outs")
    return out


TOL = {"avg": 0.0006, "obp": 0.0006, "slg": 0.0006, "iso": 0.0006, "k_pct": 0.00006,
       "bb_pct": 0.00006, "hr_pct": 0.00006, "p_per_pa": 0.0006, "sb_pct": 0.0006,
       "hem": 0.006, "era": 0.006, "whip": 0.0006, "fip": 0.006, "p_per_ip": 0.006,
       "p_per_bf": 0.0006, "sem": 0.006}


# --------------------------------------------------------------------------- #
# 1. pooled groups equal a direct recompute
# --------------------------------------------------------------------------- #
@needs_cache
def test_pooled_groups_equal_a_direct_recompute(panels):
    checked = 0
    for y, doc in panels.items():
        fip_c = doc["constants"]["fip_constant"]
        for side in ("hit", "pit"):
            rows = _rows(doc, side)
            for g in doc["group_defs"][side]:
                key = g["key"]
                if key in ("sp_innings", "rp_innings"):
                    continue
                sel = _select(side, key, rows)
                blk = doc["groups"][side][key]
                assert blk["n"] == len(sel), (y, side, key)
                want = _hit_direct(sel) if side == "hit" else _pit_direct(sel, fip_c)
                for stat, v in want.items():
                    got = blk["league"].get(stat)
                    assert _close(got, v, TOL[stat]), (y, side, key, stat, got, v)
                    checked += 1
                floor = [r for r in sel if (r["pa"] >= 100 if side == "hit" else r["outs"] >= 60)]
                assert blk["n_floor"] == len(floor), (y, side, key)
    assert checked > 2000


@needs_cache
def test_role_innings_cells_recompute_from_the_club_rows(panels):
    for y, doc in panels.items():
        teams = _rows(doc, "team")
        assert len(teams) == 30, y
        sp, rp = doc["groups"]["pit"]["sp_innings"]["league"], doc["groups"]["pit"]["rp_innings"]["league"]
        assert _close(sp["p_per_ip"], _s(teams, "sp_pit") / (_s(teams, "sp_outs") / 3), 0.006)
        assert _close(rp["p_per_ip"], _s(teams, "rp_pit") / (_s(teams, "rp_outs") / 3), 0.006)
        assert _close(sp["sp_ip_per_gs"], _s(teams, "sp_outs") / 3 / _s(teams, "sp_gs"), 0.006)
        # the club split lines carry the whole staff: sp + rp outs equal all outs
        assert _s(teams, "sp_outs") + _s(teams, "rp_outs") == _s(teams, "outs"), y


@needs_cache
def test_club_statistics_pool_and_spread(panels):
    for y, doc in panels.items():
        teams = _rows(doc, "team")
        st = doc["groups"]["team"]["clubs"]["stats"]
        assert _close(st["rs_g"]["league"], _s(teams, "rs") / _s(teams, "g"), 0.006)
        assert _close(st["p_per_pa"]["league"], _s(teams, "pit_seen") / _s(teams, "pa"), 0.0006)
        per = [t["rs"] / t["g"] for t in teams]
        assert _close(st["rs_g"]["mean"], sum(per) / len(per), 0.006)
        assert st["rs_g"]["low"][1] <= st["rs_g"]["median"] <= st["rs_g"]["high"][1]


# --------------------------------------------------------------------------- #
# 2. the FIP constant and the two identities on every completed season
# --------------------------------------------------------------------------- #
def _completed_cached():
    return [y for y in range(L.FIRST_SEASON, date.today().year + 1)
            if _have(y) and L.season_complete(y)]


@needs_cache
def test_fip_constant_equals_league_totals_on_completed_seasons(panels):
    import league_constants
    seasons = _completed_cached()
    assert len(seasons) >= 26
    for y in seasons:
        lt = league_constants.league_totals(y)
        pit = L.season_splits(y, "pitching")
        tot = {k: sum(float((s.get("stat") or {}).get(k) or 0) for s in pit)
               for k in ("earnedRuns", "outs", "homeRuns", "baseOnBalls", "hitByPitch", "strikeOuts")}
        ip = tot["outs"] / 3.0
        mine = (9 * tot["earnedRuns"] / ip
                - (13 * tot["homeRuns"] + 3 * (tot["baseOnBalls"] + tot["hitByPitch"])
                   - 2 * tot["strikeOuts"]) / ip)
        assert abs(mine - lt["fip_constant"]) <= L.FIP_TOLERANCE, (y, mine, lt["fip_constant"])
    for y, doc in panels.items():
        if not doc["complete"]:
            continue
        lt = league_constants.league_totals(y)
        assert abs(doc["constants"]["fip_constant"] - lt["fip_constant"]) <= 0.0005, y
        assert abs(doc["constants"]["fip_constant_panel"] - lt["fip_constant"]) <= 0.0005, y


@needs_cache
def test_pa_equals_bf_and_seen_equals_thrown_on_every_completed_season():
    seasons = _completed_cached()
    assert len(seasons) >= 26
    for y in seasons:
        hit, pit = L.season_splits(y, "hitting"), L.season_splits(y, "pitching")
        assert L.check_identities(hit, pit, True) == [], y
        pa = sum(s["stat"].get("plateAppearances") or 0 for s in hit)
        bf = sum(s["stat"].get("battersFaced") or 0 for s in pit)
        seen = sum(s["stat"].get("numberOfPitches") or 0 for s in hit)
        thrown = sum(s["stat"].get("numberOfPitches") or 0 for s in pit)
        assert pa == bf and seen == thrown, (y, pa, bf, seen, thrown)


# --------------------------------------------------------------------------- #
# 3. the all group reproduces the window lab's recipe
# --------------------------------------------------------------------------- #
@needs_cache
def test_completed_all_group_reproduces_the_lab_recipe(panels):
    from tools import mlbstats_window_lab as lab
    done = 0
    for y, doc in panels.items():
        if not doc["complete"]:
            continue
        memo = lab._panel_path(y)
        if not memo.exists():
            continue
        lp = json.loads(memo.read_text(encoding="utf-8"))
        lp = {k: ({int(a): b for a, b in v.items()} if k in ("hit", "pit") else v)
              for k, v in lp.items()}
        # Hitters: the lab's panel drops only zero-PA rows, so its position
        # players pool to exactly the `all` group.
        hit_only = {"hit": {m: r for m, r in lp["hit"].items() if r.get("pos") != "P"}}
        acc = lab._sum_counts({y: hit_only}, [y], "hit",
                              ("pa", "ab", "h", "2b", "3b", "hr", "bb", "ibb", "hbp",
                               "sf", "so", "sb", "cs"))
        tot = {}
        for a in acc.values():
            for k, v in a.items():
                if not k.startswith("_") and isinstance(v, float):
                    tot[k] = tot.get(k, 0.0) + v
        want = lab._hitter_rates(tot)
        got = doc["groups"]["hit"]["all"]["league"]
        for k in ("avg", "obp", "slg", "ops", "iso", "babip", "k_pct", "bb_pct"):
            assert got[k] == want[k], (y, k, got[k], want[k])
        # Pitchers: the lab's panel is the boards' pool (primary position P).
        pacc = lab._sum_counts({y: lp}, [y], "pit",
                               ("g", "gs", "outs", "tbf", "er", "r", "bb", "so", "hr", "hbp",
                                "pit", "strk", "cg", "go", "ao", "sv", "hld"))
        ptot = {}
        for a in pacc.values():
            for k, v in a.items():
                if not k.startswith("_") and isinstance(v, float):
                    ptot[k] = ptot.get(k, 0.0) + v
        pwant = lab._pitcher_rates(ptot, starter=True)
        pgot = doc["groups"]["pit"]["pitchers_only"]["league"]
        for k in ("era", "hr9", "k_pct", "bb_pct", "k_bb_pct", "gb_pct", "ip_per_gs", "strike_pct"):
            assert pgot[k] == pwant[k], (y, k, pgot[k], pwant[k])
        done += 1
    assert done >= 1, "no completed season with a memoised lab panel was checked"


@needs_cache
def test_role_anchors_from_player_splits_equal_the_club_splits(panels):
    """8.D row 2 (i): the league role anchors from the player sp/rp splits
    (pitch_rates) equal those from the club splits within 0.1 percent."""
    import pitch_rates
    done = 0
    for y, doc in panels.items():
        if y < pitch_rates.MLB_FIRST or not (CACHE / "pitch_rates" / f"pitching_sprp_1_{y}.json").exists():
            continue
        lr = pitch_rates.league_rates("MLB", y, fetch=False)
        for code, cell in (("sp", "sp_innings"), ("rp", "rp_innings")):
            a = (lr.get(code) or {}).get("p_ip")
            b = doc["groups"]["pit"][cell]["league"]["p_per_ip"]
            if a is None:
                continue
            assert abs(a - b) / a <= 0.001 + 0.005 / a, (y, code, a, b)
            done += 1
    assert done >= 2


# --------------------------------------------------------------------------- #
# 4. no grade key, no vs-hand group
# --------------------------------------------------------------------------- #
GRADE = re.compile(r"(^|_)(e?fv|grade)|fv|grade", re.I)
VS_HAND = re.compile(r"vs[_ ]?(l|r|lhp|rhp|hand)|opp(onent)?_hand|platoon", re.I)


def _keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _group_and_filter_keys(doc: dict) -> set:
    keys = set()
    for side in ("hit", "pit"):
        keys |= {g["key"] for g in doc["group_defs"][side]}
        keys |= set(doc["groups"][side])
    keys |= set(_keys(doc["filters"]))
    for side in ("hit", "pit"):
        for f in doc["filters"].get(side, {}).values():
            for v in (f.get("values") or []):
                keys.add(str(v["key"] if isinstance(v, dict) else v))
    return keys


@needs_cache
def test_no_group_or_filter_key_names_a_grade(panels):
    for y, doc in panels.items():
        bad = [k for k in _group_and_filter_keys(doc) if GRADE.search(k)]
        assert not bad, (y, bad)
    series = L.build_series(panels)
    for side, cells in series["cells"].items():
        assert not [c["key"] for c in cells if GRADE.search(c["key"])]


@needs_cache
def test_no_vs_hand_group_exists(panels):
    for y, doc in panels.items():
        keys = _group_and_filter_keys(doc)
        assert not [k for k in keys if VS_HAND.search(k)], y
        hand = [g for side in ("hit", "pit") for g in doc["group_defs"][side]
                if g["key"].startswith(("bats_", "throws_"))]
        assert hand and all("own" in g["rule"] for g in hand)
        assert {e["key"] for e in doc["notes"]["left_out"]} == {"club", "prospect_cells", "matchup_split"}
        assert all(e["reason"] for e in doc["notes"]["left_out"])


# --------------------------------------------------------------------------- #
# 5. the series
# --------------------------------------------------------------------------- #
@needs_cache
def test_series_carries_sp_ip_per_gs_beside_ip_per_gs(panels):
    series = L.build_series(panels)
    keys = {d["key"] for d in series["stats"]["pit"]}
    assert {"ip_per_gs", "sp_ip_per_gs", "p_per_ip", "p_per_bf"} <= keys
    assert {"p_per_pa", "k_pct", "bb_pct", "hr_pct"} <= {d["key"] for d in series["stats"]["hit"]}
    for y, s in series["seasons"].items():
        al = s["pit"]["all"]
        teams = _rows(panels[int(y)], "team")
        starts_only = _s(teams, "sp_outs") / 3 / _s(teams, "sp_gs")
        assert _close(al["sp_ip_per_gs"], starts_only, 0.006), y
        assert al["ip_per_gs"] > al["sp_ip_per_gs"], y      # the all-innings form, unchanged
        assert s["pit"]["sp_innings"]["sp_ip_per_gs"] == al["sp_ip_per_gs"]
        for side in ("hit", "pit"):
            assert set(s[side]) <= set(L.SERIES_CELLS[side]), (y, side)
        assert "club_mean" in s["team"] and "club_sd" in s["team"]
    assert series["war"]["label"] in ("eWAR", "fWAR", "bWAR", "WAR")


@needs_cache
def test_known_league_values_reproduce(panels):
    """The lane's measured table (league_team_stats.md section 2)."""
    for y, ppa, k, era, pip in ((2000, 3.773, 0.159, 4.77, 16.54), (2025, 3.882, 0.222, 4.16, 16.48)):
        if y not in panels:
            continue
        g = panels[y]["groups"]
        assert g["hit"]["all"]["league"]["p_per_pa"] == ppa
        assert round(g["hit"]["all"]["league"]["k_pct"], 3) == k
        assert g["pit"]["all"]["league"]["era"] == era
        assert g["pit"]["all"]["league"]["p_per_ip"] == pip


# --------------------------------------------------------------------------- #
# 6. the flag and the refusals
# --------------------------------------------------------------------------- #
def test_dark_by_default_and_the_preview_is_off_the_webroot():
    assert L.MLBSTATS_LEAGUE_TEAMS_LIVE is False
    assert L.out_dir() == L.PREVIEW_DIR
    assert L.PREVIEW_DIR.relative_to(L.ROOT / ".cache")
    assert L.DATA_DIR not in L.PREVIEW_DIR.parents


def _split(pid, stat, pos="P", team=147, lg="AL"):
    return {"season": "2019", "stat": stat, "player": {"id": pid, "fullName": f"P{pid}"},
            "team": {"id": team, "name": "New York Yankees"}, "league": {"name": lg},
            "position": {"abbreviation": pos}}


def _fixture_cache(tmp_path: Path, *, pa=10, bf=10, seen=40, thrown=40) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    hit = [_split(1, {"plateAppearances": pa, "atBats": pa, "hits": 3, "numberOfPitches": seen,
                      "age": 27, "gamesPlayed": 3}, pos="SS")]
    pit = [_split(2, {"battersFaced": bf, "outs": 9, "earnedRuns": 1, "numberOfPitches": thrown,
                      "gamesPitched": 3, "gamesStarted": 0, "strikeOuts": 3, "baseOnBalls": 1,
                      "homeRuns": 0, "hitByPitch": 0, "age": 30})]
    for g, rows in (("hitting", hit), ("pitching", pit)):
        (d / f"fa_statsapi_{g}_2019.json").write_text(
            json.dumps({"stats": [{"splits": rows}]}), encoding="utf-8")
    return d


@pytest.fixture
def offline(monkeypatch):
    """Every side input empty, league_totals solved on the fixture's sums."""
    import league_constants

    def _lt(season):
        return {"fip_constant": (9 * 1 - (3 * 1 - 2 * 3)) / 3.0}
    monkeypatch.setattr(league_constants, "league_totals", _lt)
    monkeypatch.setattr(L, "_hands", lambda s: {})
    monkeypatch.setattr(L, "_team_lines", lambda s: None)
    monkeypatch.setattr(L, "_war", lambda s, d=None: ({}, "ewar_v2"))
    monkeypatch.setattr(L, "index_values", lambda s, live, d=None: {
        "hem": {}, "wrc": {}, "sem": {}, "rem": {}, "dem": {}, "basis": {}, "board_rows": {}})


def test_a_fixture_season_builds(tmp_path, offline):
    d = _fixture_cache(tmp_path)
    doc = L.build_panel(2019, live_season=2026, cache_dir=d, today=date(2026, 10, 7))
    assert doc["complete"] is True
    assert doc["groups"]["hit"]["all"]["league"]["avg"] == 0.3
    assert doc["groups"]["pit"]["all"]["league"]["era"] == 3.0


def test_refuses_a_broken_identity_on_a_completed_season(tmp_path, offline):
    d = _fixture_cache(tmp_path, pa=10, bf=11)
    with pytest.raises(L.Refused, match="batters faced"):
        L.build_panel(2019, live_season=2026, cache_dir=d, today=date(2026, 10, 7))
    (tmp_path / "b").mkdir()
    d2 = _fixture_cache(tmp_path / "b", seen=40, thrown=41)
    with pytest.raises(L.Refused, match="pitches seen"):
        L.build_panel(2019, live_season=2026, cache_dir=d2, today=date(2026, 10, 7))


def test_the_live_season_tolerates_a_tenth_of_a_percent(tmp_path, offline):
    hit = [{"stat": {"plateAppearances": 100000, "numberOfPitches": 400000}}]
    ok = [{"stat": {"battersFaced": 100050, "numberOfPitches": 400300}}]
    far = [{"stat": {"battersFaced": 100200, "numberOfPitches": 400000}}]
    assert L.check_identities(hit, ok, complete=False) == []
    assert L.check_identities(hit, ok, complete=True) != []
    assert L.check_identities(hit, far, complete=False) != []


def test_refuses_empty_splits(tmp_path, offline):
    d = _fixture_cache(tmp_path)
    (d / "fa_statsapi_pitching_2019.json").write_text(json.dumps({"stats": [{"splits": []}]}),
                                                     encoding="utf-8")
    with pytest.raises(L.Refused, match="pitching splits came back empty"):
        L.build_panel(2019, live_season=2026, cache_dir=d, today=date(2026, 10, 7))


def test_refuses_when_under_ninety_percent_of_a_live_board_joins(tmp_path, offline, monkeypatch):
    d = _fixture_cache(tmp_path)
    monkeypatch.setattr(L, "index_values", lambda s, live, dd=None: {
        "hem": {}, "wrc": {}, "sem": {}, "rem": {}, "dem": {}, "basis": {},
        "board_rows": {"hem": [1] + list(range(100, 110))}})
    with pytest.raises(L.Refused, match="board rows join"):
        L.build_panel(2019, live_season=2019, cache_dir=d, today=date(2019, 9, 1))


def test_a_refused_season_keeps_the_last_good_file(tmp_path, offline, monkeypatch):
    d = _fixture_cache(tmp_path, pa=10, bf=11)
    out = tmp_path / "preview"
    out.mkdir()
    prior = out / "mlb_league_panel_2019.json"
    prior.write_text('{"schema": 1, "season": 2019, "complete": false, "groups": {}}\n',
                     encoding="utf-8")
    before = prior.read_bytes()
    monkeypatch.setattr(L, "cached_seasons", lambda cache_dir=None, last=None: [2019])
    s = L.export(out=out, cache_dir=d, today=date(2026, 10, 7), log=lambda *a: None)
    assert 2019 in s["refused"] and s["built"] == []
    assert prior.read_bytes() == before


def test_export_writes_only_where_it_is_told(tmp_path, offline, monkeypatch):
    d = _fixture_cache(tmp_path)
    out = tmp_path / "preview"
    monkeypatch.setattr(L, "cached_seasons", lambda cache_dir=None, last=None: [2019])
    s = L.export(out=out, cache_dir=d, today=date(2026, 10, 7), log=lambda *a: None)
    assert s["built"] == [2019] and not s["refused"]
    assert sorted(p.name for p in out.iterdir()) == ["mlb_league_panel_2019.json", SERIES_ARTIFACT]
    series = json.loads((out / SERIES_ARTIFACT).read_text(encoding="utf-8"))
    assert "2019" in series["seasons"]


def test_the_catalog_names_both_artifacts():
    import data_catalog as dc
    rows = {a["file"]: a for a in dc.ARTIFACTS}
    for name in (PANEL_ARTIFACT, SERIES_ARTIFACT):
        assert name in rows, name
        assert rows[name]["pinned_by"] == "test_league_averages_export.py"
        assert rows[name]["stability"] == dc.EXPERIMENTAL


def test_copy_carries_no_forecast_word():
    blob = json.dumps({"defs": L.STAT_DEFS, "left": L.LEFT_OUT, "def": L.DEFERRED,
                       "m": L.method_sentence()})
    for w in (" luck", " due ", "regress", "trending", " will ", "clutch", "sleeper"):
        assert w not in blob.lower(), w
    assert "\u2014" not in blob and "\u2013" not in blob
