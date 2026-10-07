# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Team Stats exporter's contract (team_stats_export.py; plan Part 8 item
P8.2, task LT-05, queue Q8_10; the lane design's section 10 with the 8.D row 2
pins).

The artifact pinned here is mlb_team_stats.json. While
league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE is False it is written only under
.cache/league_teams/preview/; nothing here writes under data/.

What is pinned:
  * the club-today block equals the four boards and war_leaderboards.json value
    for value, and a changed value is refused;
  * the earned rollups recompute from stints on a fixture (a traded player
    splits his weight; a club with no movers reads its club-today value);
  * xWinLoss wins plus losses equal games played for every club in every
    season, and agree with mlb_team_season's reader;
  * 30 clubs per sp and rp code;
  * the league role anchors from the club splits equal the player splits'
    within 0.1 percent (8.D row 2 pin i), and the earned pitch figures
    reconcile to the StatsAPI club totals (pin iii);
  * the league weighted means equal a recompute typed here;
  * the tendency cells equal the management rows verbatim, and the style z
    columns carry no value colour;
  * the six board payloads are byte-identical with and without the exporter,
    which leaves leaderboard_vintages' TEAM_COLUMNS inputs untouched;
  * no division-title field, no fit or correlation, no forecast word.

The real-data tests read the served boards and the gitignored caches and skip
when a cache is absent; nothing here opens a socket.
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

import league_averages
import team_stats_export as T

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"


def _have_caches() -> bool:
    return ((CACHE / "war_daily" / "bat.parquet").exists()
            and (CACHE / "war_daily" / "pit.parquet").exists()
            and (CACHE / "team_stats" / "2025_sprp.json").exists()
            and (CACHE / "statsapi_standings_2025.json").exists())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("team_stats_export must not open a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _parquet_frames() -> dict:
    import pandas as pd
    return {s: pd.read_parquet(CACHE / "war_daily" / f"{s}.parquet") for s in ("bat", "pit")}


@pytest.fixture(scope="module")
def frames():
    if not _have_caches():
        pytest.skip("stint frames or club caches absent")
    return _parquet_frames()


@pytest.fixture(scope="module")
def doc(frames):
    return T.build(frames=frames, log=lambda *_: None)


def _teams(name):
    blob = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    return {T._canon(t["team"]): t for t in blob["teams"]}


# --------------------------------------------------------------------------- #
# 1. club today: copied, never recomputed
# --------------------------------------------------------------------------- #
def test_club_today_values_equal_the_boards_value_for_value(doc):
    assert len(doc["teams"]) == 30
    n = 0
    for name, keys in T.ROSTER_KEYS.items():
        board = _teams(name)
        for row in doc["teams"]:
            t = board[row["club"]]
            for k in keys:
                assert row["roster"][k] == t.get(k), (name, row["club"], k)
                n += 1
            assert row["code"] == _teams("hitter_leaderboards")[row["club"]]["team"]
    assert n == 30 * sum(len(k) for k in T.ROSTER_KEYS.values())
    war = _teams(T.WAR_BOARD)
    for row in doc["teams"]:
        assert row["earned"]["war"] == war[row["club"]]["war_earned"]


def test_a_changed_club_today_value_is_refused(frames):
    roster, _sp, _st = T.roster_block()
    assert T.copy_check(roster) == []
    club = sorted(roster)[0]
    roster[club]["offense_plus"] = (roster[club]["offense_plus"] or 0) + 1
    problems = T.copy_check(roster)
    assert len(problems) == 1 and "offense_plus" in problems[0]


# --------------------------------------------------------------------------- #
# 2. the earned basis on a fixture
# --------------------------------------------------------------------------- #
def _fixture_frames():
    import pandas as pd
    bat = pd.DataFrame([
        # a hitter traded from DET to NYY: 300 PA, then 100 PA
        {"mlb_ID": 1, "year_ID": 2026, "team_ID": "DET", "PA": 300, "Inn": 600.0},
        {"mlb_ID": 1, "year_ID": 2026, "team_ID": "NYY", "PA": 100, "Inn": 200.0},
        # one club all season
        {"mlb_ID": 2, "year_ID": 2026, "team_ID": "DET", "PA": 500, "Inn": 1000.0},
        {"mlb_ID": 3, "year_ID": 2026, "team_ID": "NYY", "PA": 400, "Inn": 0.0},
        # another season and a club code that does not resolve
        {"mlb_ID": 2, "year_ID": 2025, "team_ID": "NYY", "PA": 600, "Inn": 1200.0},
        {"mlb_ID": 4, "year_ID": 2026, "team_ID": "ZZZ", "PA": 50, "Inn": 10.0},
    ])
    pit = pd.DataFrame([
        {"mlb_ID": 10, "year_ID": 2026, "team_ID": "DET", "IPouts": 300},
        {"mlb_ID": 10, "year_ID": 2026, "team_ID": "NYY", "IPouts": 150},
        {"mlb_ID": 11, "year_ID": 2026, "team_ID": "NYY", "IPouts": 90},
    ])
    return {"bat": bat, "pit": pit}


def test_earned_rollups_recompute_from_stints_on_a_fixture():
    # Board exposure differs a little from the frame's, as StatsAPI and
    # Baseball-Reference counts do: the weight is the board's, split by stint.
    index = {"basis": "fixture",
             "hem": {1: (120.0, 410.0), 2: (90.0, 500.0), 3: (100.0, 400.0), 4: (80.0, 50.0)},
             "sem": {10: (110.0, 150.0)},
             "rem": {11: (95.0, 30.0)},
             "dem": {1: (105.0, 790.0), 2: (99.0, 1000.0)}}
    out, meta = T.earned_rollups(2026, frames=_fixture_frames(), index=index,
                                 clubs={"DET", "NYY", "BOS"})
    # DET: player 1 with 3/4 of his 410 PA, player 2 whole.
    w1, w2 = 410.0 * 0.75, 500.0
    det = (120.0 * w1 + 90.0 * w2) / (w1 + w2)
    assert out["DET"]["offense_plus_raw"] == round(det, 2)
    assert out["DET"]["offense_plus"] == int(det + 0.5)
    assert out["DET"]["offense_plus_pa"] == round(w1 + w2, 1)
    nyy = (120.0 * 410.0 * 0.25 + 100.0 * 400.0) / (410.0 * 0.25 + 400.0)
    assert out["NYY"]["offense_plus_raw"] == round(nyy, 2)
    # the starter's 150 IP split 2:1; the reliever whole
    assert out["DET"]["rotation_plus_ip"] == 100.0 and out["NYY"]["rotation_plus_ip"] == 50.0
    assert out["NYY"]["bullpen_plus"] == 95 and out["DET"]["bullpen_plus"] is None
    # fielding innings split by the Inn column: player 1 600 of 800
    dem_det = (105.0 * 790.0 * 0.75 + 99.0 * 1000.0) / (790.0 * 0.75 + 1000.0)
    assert out["DET"]["team_dem_plus_raw"] == round(dem_det, 2)
    # the ZZZ stint is counted, never assigned
    assert "ZZZ" not in out and meta["families"]["offense_plus"]["unmapped_codes"] == ["ZZZ"]
    # player 4 has exposure but no resolvable club share: unassigned, counted
    assert meta["families"]["offense_plus"]["n_unassigned"] == 1
    assert meta["families"]["offense_plus"]["exposure"] == round(410 + 500 + 400 + 50, 1)


def test_a_club_with_no_movers_reads_its_club_today_value_on_the_earned_basis():
    """With one membership the two bases agree: a club none of whose players
    changed clubs reads the club-today formula (board exposure, board club)."""
    import pandas as pd
    bat = pd.DataFrame([
        {"mlb_ID": 5, "year_ID": 2026, "team_ID": "BOS", "PA": 610, "Inn": 1300.0},
        {"mlb_ID": 6, "year_ID": 2026, "team_ID": "BOS", "PA": 220, "Inn": 400.0},
        {"mlb_ID": 7, "year_ID": 2026, "team_ID": "TBR", "PA": 90, "Inn": 100.0},
        {"mlb_ID": 7, "year_ID": 2026, "team_ID": "MIA", "PA": 90, "Inn": 100.0},
    ])
    index = {"basis": "fixture", "hem": {5: (131.0, 600.0), 6: (88.0, 221.0), 7: (100.0, 180.0)},
             "sem": {}, "rem": {}, "dem": {}}
    out, _meta = T.earned_rollups(2026, frames={"bat": bat, "pit": bat}, index=index,
                                  clubs={"BOS", "TBR", "MIA"})
    club_today = (131.0 * 600.0 + 88.0 * 221.0) / (600.0 + 221.0)
    assert out["BOS"]["offense_plus_raw"] == round(club_today, 2)
    assert out["BOS"]["offense_plus_pa"] == 821.0
    assert out["TBR"]["offense_plus_pa"] == out["MIA"]["offense_plus_pa"] == 90.0


# --------------------------------------------------------------------------- #
# 3. records
# --------------------------------------------------------------------------- #
def test_xwinloss_sums_to_games_played_for_every_club_in_every_season(doc):
    import mlb_team_season
    seen = 0
    for y in range(T.FIRST_SEASON, doc["live_season"] + 1):
        if not (CACHE / f"statsapi_standings_{y}.json").exists():
            continue
        rec = T.records(y)
        assert len(rec) == 30
        other = mlb_team_season.expected_records(y)
        for club, r in rec.items():
            assert r["xw"] + r["xl"] == r["g"], (y, club)
            assert (r["xw"], r["xl"], r["g"]) == (other[club]["xw"], other[club]["xl"],
                                                  other[club]["g"]), (y, club)
            assert r["w_minus_xw"] == r["w"] - r["xw"]
        seen += 1
    assert seen >= 26
    for row in doc["teams"]:
        assert row["xw"] + row["xl"] == row["g"]
        assert row["lg"] in ("AL", "NL")


def test_a_club_whose_xwinloss_misses_games_played_is_refused():
    rows = {f"C{i:02d}": {2026: {"w": 81, "l": 81, "rs": 1, "ra": 1, "rd": 0, "gp": 162,
                                 "xw": 80, "xl": 82, "league_id": 103,
                                 "one_run": [1, 1], "extra_inning": None}}
            for i in range(30)}
    assert len(T.records(2026, rows)) == 30
    rows["C07"][2026]["xl"] = 81
    with pytest.raises(T.Refused, match="C07"):
        T.records(2026, rows)


def test_the_payload_carries_no_division_title_field(doc):
    blob = json.dumps(doc)
    for k in ("div_champ", "divisionChamp", "division_champ", "clinched", "division_id"):
        assert f'"{k}"' not in blob, k


# --------------------------------------------------------------------------- #
# 4. pitch counts and PAR
# --------------------------------------------------------------------------- #
def test_thirty_clubs_per_sp_and_rp_code(frames):
    import mlb_team_season
    for y in range(T.FIRST_SEASON, 2027):
        try:
            lines = mlb_team_season.team_lines(y)
        except mlb_team_season.NotCached:
            continue
        assert len(lines["sp"]) == 30 and len(lines["rp"]) == 30, y
        assert set(lines["sp"]) == set(lines["rp"]) == set(lines["pit"]), y


def test_league_role_anchors_from_club_splits_equal_the_player_splits(doc):
    a = doc["league"]["anchors"]
    assert a["checked"] is True
    for code in ("sp", "rp"):
        assert a[code]["rel_diff"] <= T.ANCHOR_TOLERANCE, code
    # a completed season too
    import mlb_team_season
    a25 = T.anchor_check(mlb_team_season.team_lines(2025), 2025)
    assert a25["checked"] is True
    for code in ("sp", "rp"):
        assert a25[code]["rel_diff"] <= T.ANCHOR_TOLERANCE


def test_earned_pitch_figures_reconcile_to_the_club_totals(doc):
    import mlb_team_season
    lines = mlb_team_season.team_lines(doc["season"])
    for row in doc["teams"]:
        p, h, pit = row["pitches"], lines["hit"][row["club"]], lines["pit"][row["club"]]
        sp, rp = lines["sp"][row["club"]], lines["rp"][row["club"]]
        assert p["pa"] == h["pa"] and p["pit_seen"] == h["pitches"]
        assert p["pit_thrown"] == pit["pitches"]
        assert sp["outs"] + rp["outs"] == pit["outs"]
        assert p["p_per_pa"] == round(h["pitches"] / h["pa"], 3)
        assert p["p_per_ip"] == round(pit["pitches"] / (pit["outs"] / 3), 2)
        assert p["sp_p_per_ip"] == round(sp["pitches"] / (sp["outs"] / 3), 2)
        assert p["rp_p_per_ip"] == round(rp["pitches"] / (rp["outs"] / 3), 2)
        # starts only, never the served all-innings ip_per_gs
        assert p["sp_ip_per_gs"] == round(sp["outs"] / 3 / sp["gs"], 2)
        assert p["relief_ip_share"] == round(rp["outs"] / pit["outs"], 3)


def test_team_par_averages_one_hundred_over_the_clubs(doc):
    for k, v in doc["league"]["pitches"]["par_mean"].items():
        assert abs(v - 100.0) < 1e-6, k
    rates = {r["club"]: r["pitches"]["sp_p_per_ip"] for r in doc["teams"]}
    mean = sum(rates.values()) / 30
    for r in doc["teams"]:
        # the stored rate is rounded; PAR is computed on the unrounded one
        assert abs(r["pitches"]["rotation_par"] - 100 * rates[r["club"]] / mean) <= 0.6


# --------------------------------------------------------------------------- #
# 5. league means, depth
# --------------------------------------------------------------------------- #
def test_league_weighted_means_equal_a_recompute(doc):
    want = {"offense_plus_pa_weighted": ("hitter_leaderboards", "offense_plus_raw", "team_pa"),
            "rotation_plus_ip_weighted": ("starter_leaderboards", "rotation_plus_raw", "starter_ip"),
            "bullpen_plus_ip_weighted": ("bullpen_leaderboards", "bullpen_plus_raw", "relief_ip"),
            "team_dem_plus_inn_weighted": ("defense_leaderboards", "team_dem_plus_raw", "team_inn")}
    got = doc["league"]["roster"]["means"]
    for key, (name, v, w) in want.items():
        ts = list(_teams(name).values())
        assert got[key] == round(sum(t[v] * t[w] for t in ts) / sum(t[w] for t in ts), 2), key
    # the earned means over the same players: every scored player is assigned,
    # so the league totals match the club-today means within rounding
    em = doc["league"]["earned"]["means"]
    for key in want:
        assert abs(em[key] - got[key]) <= 0.05, key


def test_depth_recomputes_from_the_offense_rows(doc):
    hit = json.loads((DATA / "hitter_leaderboards.json").read_text(encoding="utf-8"))
    for row in doc["teams"]:
        rows = [r for r in hit["hitters"] if r["team"] == row["code"]
                and r.get("hem_plus") is not None and r.get("pa")]
        d = row["depth"]
        assert d["heart_hem"] == row["roster"]["heart_hem"]
        tot = sum(r["pa"] for r in rows)
        assert d["pa_share_hem_100"] == round(sum(r["pa"] for r in rows if r["hem_plus"] >= 100) / tot, 3)
        front = _front(rows)
        assert d["n_rest"] == len(rows) - len(front)
        rest = _rest(rows)
        assert d["rest_hem"] == round(rest, 1)
        assert d["gap"] == round(d["heart_hem"] - rest, 1)


def _front(rows):
    return sorted([r for r in rows if r["pa"] >= 200], key=lambda r: (-r["hem_plus"], -r["pa"]))[:3]


def _rest(rows):
    keys = {r["mlbam"] for r in _front(rows)}
    rest = [r for r in rows if r["mlbam"] not in keys]
    return sum(r["hem_plus"] * r["pa"] for r in rest) / sum(r["pa"] for r in rest)


# --------------------------------------------------------------------------- #
# 6. tendencies
# --------------------------------------------------------------------------- #
def test_tendency_cells_equal_the_management_rows(doc):
    mg = json.loads((DATA / "management_board.json").read_text(encoding="utf-8"))
    clubs = {T._canon(r["club"]): r for r in mg["clubs"]["rows"] if r["season"] == doc["season"]}
    teams = {T._canon(r["team"]): r for r in mg["teams"]["rows"] if r["season"] == doc["season"]}
    n = 0
    for row in doc["teams"]:
        t = row["tendencies"]
        for k, v in t["style"].items():
            assert v == clubs[row["club"]][k], (row["club"], k)
            n += 1
        for k, v in t["running"].items():
            assert v == teams[row["club"]][k], (row["club"], k)
            n += 1
        for k in T.STYLE_Z_KEYS:
            assert k in t["style"]
    assert n > 30 * 20
    copy = doc["copy"]["tendencies"]
    assert copy["style_sentence"] == mg["clubs"]["style_sentence"]
    assert copy["why_no_plus_metric"] == mg["sections"]["team_style"]["why_no_plus_metric"]
    # style z columns carry no value colour and no ruler
    assert set(doc["columns"]["no_value_colour"]) == set(T.STYLE_Z_KEYS)
    assert not set(T.STYLE_Z_KEYS) & set(doc["columns"]["value_ruler"])
    # realized family values are copied one by one, never summed
    assert not any(k.startswith("mwpa_total") or k == "mwpa" for r in doc["teams"]
                   for k in r["tendencies"]["style"])


# --------------------------------------------------------------------------- #
# 7. served files untouched; dark by default
# --------------------------------------------------------------------------- #
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_six_boards_are_byte_identical_with_and_without_the_exporter(frames, tmp_path):
    paths = [DATA / f"{n}.json" for n in T.SIX_BOARDS]
    before = {p.name: _sha(p) for p in paths}
    s = T.export(out=tmp_path, frames=frames, log=lambda *_: None)
    assert s["written"] and s["refused"] is None
    assert {p.name: _sha(p) for p in paths} == before
    # the leaderboard_vintages TEAM_COLUMNS inputs are three of those boards
    import leaderboard_vintages as LV
    assert set(LV.SOURCES) <= {p.name for p in paths}
    assert "leaderboard_vintages" not in (ROOT / "team_stats_export.py").read_text(encoding="utf-8")
    assert sorted(x.name for x in tmp_path.iterdir()) == [T.OUT_NAME]


def test_dark_by_default_and_the_preview_is_off_the_webroot():
    assert league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE is False
    assert T.out_path() == league_averages.PREVIEW_DIR / T.OUT_NAME
    assert T.DATA_DIR not in T.out_path().parents
    assert not (DATA / T.OUT_NAME).exists()


def test_a_thinner_payload_does_not_overwrite_the_last_good_file(frames, tmp_path):
    s = T.export(out=tmp_path, frames=frames, log=lambda *_: None)
    assert s["written"]
    path = tmp_path / T.OUT_NAME
    prior = json.loads(path.read_text(encoding="utf-8"))
    prior["history"]["seasons"]["1999"] = prior["history"]["seasons"]["2000"]
    path.write_text(json.dumps(prior), encoding="utf-8")
    s2 = T.export(out=tmp_path, frames=frames, log=lambda *_: None)
    assert s2["written"] is False and "thinner" in s2["refused"]


# --------------------------------------------------------------------------- #
# 8. history, F-SCORE hook, honesty
# --------------------------------------------------------------------------- #
def test_history_covers_the_completed_seasons_on_the_earned_basis(doc):
    h = doc["history"]
    assert h["refused"] == {}
    assert sorted(h["seasons"]) == [str(y) for y in range(T.FIRST_SEASON, doc["live_season"])]
    i = {c: n for n, c in enumerate(h["cols"])}
    for y, s in h["seasons"].items():
        assert len(s["rows"]) == 30, y
        for r in s["rows"]:
            assert r[i["xw"]] + r[i["xl"]] == r[i["g"]], (y, r[0])
        has_index = s["index_basis"] is not None
        assert any(r[i["offense_plus"]] is not None for r in s["rows"]) == has_index, y
    assert h["seasons"]["2025"]["index_basis"] is not None
    assert h["seasons"]["2000"]["index_basis"] is None


def test_fscore_join_copies_verbatim_or_says_it_is_pending(tmp_path):
    rows, meta = T.fscore_join(tmp_path)
    assert rows is None and meta["joined"] is False
    blob = {"generated_at": "x", "as_of": "2026-09-30",
            "clubs": {"LAD": {"score": 127.7, "rank": 1, "letter": "A+", "raw": 0.3},
                      "CWS": {"score": 81.0, "rank": 29, "letter": "D"}}}
    (tmp_path / "fscore.json").write_text(json.dumps(blob), encoding="utf-8")
    rows, meta = T.fscore_join(tmp_path)
    assert meta["joined"] is True and meta["n"] == 2
    assert rows["LAD"] == {"score": 127.7, "letter": "A+", "rank": 1}
    assert rows["CHW"] == {"score": 81.0, "letter": "D", "rank": 29}
    for club, v in rows.items():
        src = blob["clubs"]["CWS" if club == "CHW" else club]
        assert all(v[k] == src[k] for k in T.FSCORE_KEYS)


def test_no_fit_correlation_or_forecast_word(doc):
    keys = json.dumps(doc).lower()
    for k in ('"corr', '"slope', '"r2"', '"pearson', '"spearman', '"fit"', '"rho"'):
        assert k not in keys, k
    blob = json.dumps({"copy": T.COPY, "basis": doc["basis"]}).lower()
    for w in (" luck", " due ", "regress", "trending", " will ", "clutch", "sleeper"):
        assert w not in blob, w
    src = (ROOT / "team_stats_export.py").read_text(encoding="utf-8")
    assert "\u2014" not in src and "\u2013" not in src
    assert "\u2014" not in json.dumps(doc, ensure_ascii=False)


def test_the_registry_describes_the_five_served_rollups():
    import model_registry
    reg = model_registry.load()
    rows = {m["model_id"]: m for m in reg["models"]}
    for mid in ("offense_plus", "rotation_plus", "bullpen_plus", "leverage_deploy_plus",
                "team_dem_plus"):
        m = rows[mid]
        assert m["verdict"] == "provisional"
        assert m["provisional_kind"] == "inherits_parent_gate"
        assert m["eval_artifact"] is None
        assert m["predicts"].startswith("nothing; a descriptive weighted mean of ")
        assert "inherits" in m["baseline"] and "inherits" in m["metric"]
        assert "earned" not in json.dumps(m).lower()
        assert "teams tab" not in json.dumps(m).lower()
    assert model_registry.validate(reg) == []
