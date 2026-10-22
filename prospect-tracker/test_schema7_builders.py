# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The starter-workload dark builder (betting_usage and its seam in leaderboard_vintages),
pinned to its section by TITLE and column names, never by a letter or a literal schema
number.

docs/diamond-betting.md, "Starter workload: expected outs and pitches per start": pitcher
columns sp_n365, sp_budget, sp_ppo, sp_xouts and team column bat_ppa_l30, off
.cache/game_feeds dated strictly before the vintage date, on the priors stage 1 froze,
built only on a stage-1 PASS. Its "### Builder landed" amendment names the schema number
and the first vintage night.

What this file holds: the strictly-before rule; the floors (a real zero count, the
shrink to the anchors at n = 0, the 27-out cap, the anchor floor); incomplete and missing
feeds excluded and counted; parity with the play corpus on one 2025 game and one 2026
game; the basis stamp; the clock; old records and inputs_as_of; and that no served path
reads a column, by AST and by string. The synthetic feeds are invented; the two parity
games compare two derivations of the same counts and relate nothing to an outcome.
"""
from __future__ import annotations

import ast
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import betting_model as bm
import betting_usage as bu
import leaderboard_vintages as lv
from test_betting_workload_registration import COLUMNS, TITLE, _norm, _section

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / ".cache" / "pbp_corpus"
WIN_PROB = ROOT / ".cache" / "win_prob"
FEEDS = ROOT / ".cache" / "game_feeds"

PITCHER_COLS = ("sp_n365", "sp_budget", "sp_ppo", "sp_xouts")
TEAM_COLS = ("bat_ppa_l30",)
#: The two parity games: a 2025 corpus game (its feed is the payload the corpus was
#: built from) and a 2026 game whose cached live feed is in .cache/game_feeds.
PARITY_2025 = (778563, "2025-03-18", "CHC", "LAD")
PARITY_2026 = (822722, "2026-06-14")

D = "2026-06-01"                    # the fixture vintage date
RELIEF = 9001                       # the synthetic reliever


# ---------------------------------------------------------------------------
# synthetic feeds
# ---------------------------------------------------------------------------
def _feed(home_sp, away_sp, *, home_inn=6, away_inn=5, ppp=4, final=True,
          stamp="20260101_000000", non_pa=False):
    """A nine-inning game, three plays a half, `ppp` pitches a play, every play an out.
    The home starter works the top of the first `home_inn` innings, the away starter
    the bottom of the first `away_inn`. `non_pa` adds a caught-stealing play (one
    pitch, one out, no PA) as the top of the first's last out."""
    plays, abi = [], 0
    for inn in range(1, 10):
        for half in ("top", "bottom"):
            sp, n_inn = (home_sp, home_inn) if half == "top" else (away_sp, away_inn)
            pid = sp if inn <= n_inn else RELIEF
            for o in (1, 2, 3):
                et, n = "field_out", ppp
                if non_pa and inn == 1 and half == "top" and o == 3:
                    et, n = "caught_stealing_2b", 1
                plays.append({
                    "atBatIndex": abi,
                    "about": {"inning": inn, "halfInning": half},
                    "count": {"outs": o},
                    "matchup": {"pitcher": {"id": pid}, "batter": {"id": 5000 + abi}},
                    "result": {"eventType": et, "homeScore": 0, "awayScore": 0},
                    "playEvents": [{"isPitch": True}] * n})
                abi += 1
    return {"gameData": {"status": {"abstractGameState": "Final" if final else "Live"}},
            "liveData": {"plays": {"allPlays": plays}},
            "metaData": {"timeStamp": stamp}}


class League:
    """Synthetic games and feeds in a tmp dir, the completed-games row shape."""

    def __init__(self, root: Path):
        self.dir = root / "feeds"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.games: list[dict] = []
        self.pk = 100000

    def add(self, day, home, away, home_sp, away_sp, *, write=True, **kw):
        self.pk += 1
        self.games.append({"game_pk": self.pk, "season": day[:4], "date": day,
                           "home_org": home, "away_org": away,
                           "home_runs": 99, "away_runs": 99})
        if write:
            (self.dir / f"{self.pk}.json").write_text(
                json.dumps(_feed(home_sp, away_sp, **kw)), encoding="utf-8")
        return self.pk


def _days(d0: str, k: int) -> str:
    return (date.fromisoformat(d0) + timedelta(days=k)).isoformat()


def _artifact(tmp: Path, verdict="PASS", priors=None, status="complete") -> Path:
    p = tmp / "starter_workload_eval.json"
    p.write_text(json.dumps({"stage1": {
        "status": status, "verdict": verdict,
        "burn_in": {"priors": dict(priors or {"k_b": 2, "k_o": 120, "k_l": 300,
                                               "k_c": 2})}}}), encoding="utf-8")
    return p


@pytest.fixture
def lg(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, "SW_MIN_ANCHOR_GAMES", 2)
    bu._SW_MEMO.clear()
    league = League(tmp_path)
    # two anchor-season games (2025), one inside the 365-day window of D and one not
    league.add("2025-05-01", "NYY", "BOS", 11, 21, home_inn=7, away_inn=7, ppp=3)
    league.add("2025-07-01", "NYY", "BOS", 11, 21, home_inn=6, away_inn=5, ppp=4)
    # the season before D
    league.add(_days(D, -40), "NYY", "BOS", 11, 22, home_inn=5, away_inn=6, ppp=5)
    league.add(_days(D, -30), "NYY", "SEA", 12, 31, home_inn=6, away_inn=6, ppp=4)
    league.add(_days(D, -1), "SEA", "BOS", 31, 21, home_inn=4, away_inn=8, ppp=4)
    yield league
    bu._SW_MEMO.clear()


def _build(league, tmp_path, pitchers=("11", "12", "21", "22", "31", "77"),
           on_date=D, **kw):
    if "artifact_path" not in kw:
        kw["artifact_path"] = _artifact(tmp_path)
    return bu.build_schema7_workload_columns(
        {p: None for p in pitchers}, on_date=on_date, orgs=["NYY", "BOS", "SEA", "TOR"],
        games=league.games, feed_dir=league.dir, tally_path=tmp_path / "memo.json", **kw)


def _anchors(league, season="2025"):
    """The anchors recomputed by hand from the feed specs, sum over sum."""
    starts = sp = so = bp = bpa = 0
    for g in league.games:
        if g["season"] != season:
            continue
        t = bu.workload_from_plays(json.loads(
            (league.dir / f"{g['game_pk']}.json").read_text(encoding="utf-8"))
            ["liveData"]["plays"]["allPlays"])
        for side in ("home", "away"):
            starts += 1
            sp += t["sp"][side][1]
            so += t["sp"][side][2]
            bp += t["bat"][side][0]
            bpa += t["bat"][side][1]
    return sp / starts, sp / so, bp / bpa


# ---------------------------------------------------------------------------
# 1. the section, the names, the schema number and the priors, by title
# ---------------------------------------------------------------------------
def _landed() -> tuple[str, str]:
    sec = _section()
    m = re.search(r"^### Builder landed (20\d\d-\d\d-\d\d)[^\n]*\n(.*?)(?=^### |^---|\Z)",
                  sec, flags=re.M | re.S)
    assert m, f"the section titled {TITLE!r} has no dated '### Builder landed' amendment"
    return m.group(1), _norm(m.group(0))


def test_the_builder_landed_amendment_names_the_schema_the_code_carries():
    _d, text = _landed()
    nums = {int(n) for n in re.findall(r"\bschema (\d+)\b", text)}
    assert lv.SW_SCHEMA in nums, (
        f"the amendment must name the schema the builder rides; code says {lv.SW_SCHEMA}")
    assert lv.SW_SCHEMA == lv.SCHEMA, "the workload builder is the last landed builder"
    for col in COLUMNS:
        assert f"`{col}`" in text, col
    for needle in ("build_schema7_workload_columns", "leaderboard_vintages",
                   "starter_workload_xouts_candidate", "test_schema7_builders.py",
                   "First vintage night"):
        assert needle in text, needle


def test_the_priors_are_the_frozen_ones_in_code_section_and_artifact():
    assert bu.SW_PRIORS == {"k_b": 2, "k_o": 120, "k_l": 300}
    _d, text = _landed()
    assert "k_b 2, k_o 120, k_l 300" in text
    art = ROOT / "data" / "starter_workload_eval.json"
    if art.exists():
        s1 = json.loads(art.read_text(encoding="utf-8"))["stage1"]
        assert s1["verdict"] == "PASS"
        assert {k: s1["burn_in"]["priors"][k] for k in bu.SW_PRIORS} == bu.SW_PRIORS
        # the gate reads the real artifact the same way
        pri, _why = bu.sw_stage1_gate(art)
        assert pri == bu.SW_PRIORS


def test_the_columns_are_the_registered_names_in_every_copy():
    assert tuple(COLUMNS) == PITCHER_COLS + TEAM_COLS
    assert lv.SW_PITCHER_COLUMNS == bu.SW_PITCHER_COLUMNS == bm.DARK7_PITCHER_COLUMNS \
        == PITCHER_COLS
    assert lv.SW_TEAM_COLUMNS == bu.SW_TEAM_COLUMNS == bm.DARK7_TEAM_COLUMNS == TEAM_COLS
    assert lv.PITCHER_COLUMNS[-4:] == PITCHER_COLS
    assert lv.TEAM_COLUMNS[-1:] == TEAM_COLS
    assert bm.DARK_TEAM_COLUMNS_BY_SCHEMA[lv.SW_SCHEMA] == TEAM_COLS
    assert bm.DARK_TEAM_COLUMNS[-1:] == TEAM_COLS
    # the pitcher tuple stays out of the eval artifact's schema-3 block
    assert not set(PITCHER_COLS) & set(bm.DARK_PITCHER_COLUMNS)
    for c in COLUMNS:
        assert c in lv.FEATURE_SOURCES
        assert lv._COLUMN_ADDED[c] == (lv.SW_SCHEMA, lv.SW_ADDED)


def test_the_pa_rule_is_the_corpus_rule():
    import mlbstats_games
    assert bu.NON_PA_PREFIX == mlbstats_games.NON_PA_PREFIX


# ---------------------------------------------------------------------------
# 2. the gate: no stage-1 PASS, no column and no feed opened
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["absent", "fail", "below_floor", "priors", "partial"])
def test_no_column_is_built_without_a_stage_1_pass(kind, lg, tmp_path, monkeypatch):
    if kind == "absent":
        art = tmp_path / "nothing.json"
    elif kind == "fail":
        art = _artifact(tmp_path, verdict="FAIL")
    elif kind == "below_floor":
        art = _artifact(tmp_path, verdict="PASS-BELOW-FLOOR")
    elif kind == "priors":
        art = _artifact(tmp_path, priors={"k_b": 4, "k_o": 120, "k_l": 300})
    else:
        art = _artifact(tmp_path, status="burn_in_frozen")

    def boom(*a, **k):
        raise AssertionError("a feed was opened without a stage-1 PASS")
    monkeypatch.setattr(bu, "_feed", boom)
    out = _build(lg, tmp_path, artifact_path=art)
    assert out["basis"]["status"] == "not built"
    for c in COLUMNS:
        assert out[c]["values"] == {} and out[c]["basis"].startswith("ABSENT")
    assert not (tmp_path / "memo.json").exists()


# ---------------------------------------------------------------------------
# 3. the values, the floors and the strictly-before rule
# ---------------------------------------------------------------------------
def test_the_values_are_the_registered_formulas(lg, tmp_path):
    out = _build(lg, tmp_path)
    L_pgs, L_ppo, L_ppa = _anchors(lg)
    a = out["basis"]["anchors"]
    assert a["season"] == 2025 and a["games"] == 2 and a["starts"] == 4
    assert a["L_pgs"] == pytest.approx(L_pgs) and a["L_ppo"] == pytest.approx(L_ppo)
    assert a["L_ppa"] == pytest.approx(L_ppa)
    # pitcher 11: the 2025-07-01 start (6 inn, 4 ppp) and the D-40 start (5 inn, 5 ppp);
    # the 2025-05-01 start is older than 365 days
    n, pit, outs = 2, 6 * 3 * 4 + 5 * 3 * 5, 6 * 3 + 5 * 3
    assert out["sp_n365"]["values"]["11"] == n
    b = (pit + 2 * L_pgs) / (n + 2)
    q = (pit + 120 * L_ppo) / (outs + 120)
    assert out["sp_budget"]["values"]["11"] == pytest.approx(b, abs=1e-4)
    assert out["sp_ppo"]["values"]["11"] == pytest.approx(q, abs=1e-5)
    assert out["sp_xouts"]["values"]["11"] == pytest.approx(min(27.0, b / q), abs=1e-4)
    # the club window D - 30 to D - 1: NYY batted the bottom on D-30 (27 PA, 4 ppp);
    # its D-40 game is outside the window
    nyy = (27 * 4 + 300 * L_ppa) / (27 + 300)
    assert out["bat_ppa_l30"]["values"]["NYY"] == pytest.approx(nyy, abs=1e-5)
    bos = (27 * 4 + 300 * L_ppa) / (27 + 300)        # the top of D-1
    assert out["bat_ppa_l30"]["values"]["BOS"] == pytest.approx(bos, abs=1e-5)
    # the candidate function, which nothing served calls
    x = bu.starter_workload_xouts_candidate(b, q, nyy, L_ppa)
    assert x == pytest.approx(min(27.0, b / (q * nyy / L_ppa)))
    assert bu.starter_workload_xouts_candidate(b, q, None, L_ppa) is None


def test_the_floors(lg, tmp_path, monkeypatch):
    out = _build(lg, tmp_path)
    L_pgs, L_ppo, L_ppa = _anchors(lg)
    # a pitcher with no start: n = 0 is a real count, and the shrink sits on the anchors
    assert out["sp_n365"]["values"]["77"] == 0
    assert out["sp_budget"]["values"]["77"] == pytest.approx(L_pgs, abs=1e-4)
    assert out["sp_ppo"]["values"]["77"] == pytest.approx(L_ppo, abs=1e-5)
    # a club with no game in 30 days sits on the league rate, its raw counts zero
    assert out["bat_ppa_l30"]["values"]["TOR"] == pytest.approx(L_ppa, abs=1e-5)
    assert out["basis"]["clubs_raw"]["values"]["TOR"] == [0, 0, 0]
    # the 27-out cap
    assert bu.starter_workload_xouts_candidate(400.0, 1.0, 3.9, 3.9) == 27.0
    # the anchor floor: under it the four anchored columns are stated nulls, the count
    # still counts
    bu._SW_MEMO.clear()
    monkeypatch.setattr(bu, "SW_MIN_ANCHOR_GAMES", 3)
    out = _build(lg, tmp_path)
    assert out["basis"]["anchored"] is False
    assert out["sp_n365"]["values"]["11"] == 2
    for c in ("sp_budget", "sp_ppo", "sp_xouts", "bat_ppa_l30"):
        assert out[c]["values"] == {}
        assert "under the 3-game anchor floor" in out[c]["basis"]


def test_strictly_before_the_vintage_date(lg, tmp_path):
    base = _build(lg, tmp_path)
    # games ON and AFTER the vintage date move nothing
    lg.add(D, "NYY", "BOS", 11, 21, home_inn=9, away_inn=9, ppp=9)
    lg.add(_days(D, 1), "NYY", "SEA", 12, 31, home_inn=9, away_inn=9, ppp=9)
    bu._SW_MEMO.clear()
    later = _build(lg, tmp_path)
    for c in COLUMNS:
        assert later[c]["values"] == base[c]["values"], c
    assert later["basis"]["feeds_window"]["n_games"] == base["basis"]["feeds_window"][
        "n_games"]
    # the edges: D - 365 is in the starter's window and D - 366 is not
    lg.add(_days(D, -365), "TOR", "BOS", 61, 21, home_inn=6, away_inn=6)
    lg.add(_days(D, -366), "TOR", "BOS", 62, 21, home_inn=6, away_inn=6)
    bu._SW_MEMO.clear()
    edge = _build(lg, tmp_path, pitchers=("61", "62"))
    assert edge["sp_n365"]["values"] == {"61": 1, "62": 0}
    # D - 30 is in the club's window and D - 31 is not
    lg2 = League(tmp_path / "b")
    lg2.pk = lg.pk + 1000
    lg2.games = [g for g in lg.games if g["season"] == "2025"]
    for g in lg2.games:
        (lg2.dir / f"{g['game_pk']}.json").write_bytes(
            (lg.dir / f"{g['game_pk']}.json").read_bytes())
    lg2.add(_days(D, -30), "TOR", "SEA", 1, 2, ppp=6)
    lg2.add(_days(D, -31), "BOS", "NYY", 3, 4, ppp=6)
    bu._SW_MEMO.clear()
    o2 = _build(lg2, tmp_path, pitchers=())
    raw = o2["basis"]["clubs_raw"]["values"]
    assert raw["TOR"][2] == 1 and raw["SEA"][2] == 1
    assert raw["BOS"][2] == 0 and raw["NYY"][2] == 0


def test_incomplete_and_missing_feeds_are_excluded_and_counted(lg, tmp_path):
    lg.add(_days(D, -2), "NYY", "BOS", 11, 21, final=False)
    lg.add(_days(D, -3), "NYY", "BOS", 11, 21, write=False)
    out = _build(lg, tmp_path)
    fw = out["basis"]["feeds_window"]
    assert fw["n_incomplete"] == 1 and fw["n_missing_feed"] == 1
    assert fw["n_games"] == fw["n_complete"] + 2
    assert out["sp_n365"]["values"]["11"] == 2          # neither added a start
    assert "1 incomplete, excluded" in out["sp_n365"]["basis"]
    memo = json.loads((tmp_path / "memo.json").read_text(encoding="utf-8"))
    assert str(lg.pk - 1) not in memo["games"] and str(lg.pk) not in memo["games"]
    # the incomplete game goes final: the next night tallies it
    (lg.dir / f"{lg.pk - 1}.json").write_text(json.dumps(_feed(11, 21)), encoding="utf-8")
    out = _build(lg, tmp_path)
    assert out["sp_n365"]["values"]["11"] == 3
    assert out["basis"]["feeds_window"]["n_incomplete"] == 0


def test_a_play_without_a_pa_counts_its_pitches_and_outs_but_no_pa():
    t = bu.workload_from_plays(_feed(1, 2, non_pa=True, ppp=4)["liveData"]["plays"][
        "allPlays"])
    assert t["sp"]["home"] == [1, 6 * 3 * 4 - 3, 18]
    assert t["bat"]["away"] == [27 * 4 - 3, 26]
    assert t["bat"]["home"] == [27 * 4, 27]


# ---------------------------------------------------------------------------
# 4. parity with the play corpus, one 2025 game and one 2026 game
# ---------------------------------------------------------------------------
def _corpus_game(season: int, pk: int):
    pq = pytest.importorskip("pyarrow.parquet")
    pl_path = CORPUS / "plays" / str(season) / f"plays-{season}.parquet"
    pt_path = CORPUS / "pitches" / str(season) / f"pitches-{season}.parquet"
    if not (pl_path.exists() and pt_path.exists()):
        pytest.skip(f"the {season} corpus is not on this box")
    plays = pq.read_table(pl_path, columns=["game_pk", "season", "half", "at_bat_index",
                                            "batter_id", "pitcher_id", "event_type",
                                            "outs_before", "outs_after"],
                          filters=[("game_pk", "=", pk)])
    pitches = pq.read_table(pt_path, columns=["game_pk", "season", "at_bat_index",
                                              "is_pitch"],
                            filters=[("game_pk", "=", pk)])
    return plays, pitches


def _corpus_tally(plays, pitches) -> dict:
    """The stage-1 lab's rules on the corpus rows, written out independently: a pitch
    belongs to its play's pitcher; outs are outs_after minus outs_before; a start is
    the first play's pitcher of each half by at_bat_index."""
    npc: dict = {}
    for r in pitches.to_pylist():
        if r["is_pitch"]:
            npc[r["at_bat_index"]] = npc.get(r["at_bat_index"], 0) + 1
    rows = sorted(plays.to_pylist(), key=lambda r: r["at_bat_index"])
    first, lines = {}, {"top": {}, "bottom": {}}
    bat = {"top": [0, 0], "bottom": [0, 0]}
    for r in rows:
        h = r["half"]
        if h not in ("top", "bottom"):
            continue
        n = npc.get(r["at_bat_index"], 0)
        ob = r["outs_before"] or 0
        oa = r["outs_after"] if r["outs_after"] is not None else ob
        outs = max(0, oa - ob)
        first.setdefault(h, r["pitcher_id"])
        if r["pitcher_id"] is not None:
            ln = lines[h].setdefault(r["pitcher_id"], [0, 0])
            ln[0] += n
            ln[1] += outs
        bat[h][0] += n
        bat[h][1] += 1 if bu.is_pa_event(r["event_type"]) else 0

    def st(h):
        p = first.get(h)
        return None if p is None else [int(p), lines[h][p][0], lines[h][p][1]]
    return {"sp": {"home": st("top"), "away": st("bottom")},
            "bat": {"home": bat["bottom"], "away": bat["top"]}}


def test_parity_with_the_corpus_on_a_2025_game():
    pk, day, home, away = PARITY_2025
    payload = WIN_PROB / f"{pk}.json"
    if not payload.exists():
        pytest.skip("the 2025 payload cache is not on this box")
    plays, pitches = _corpus_game(2025, pk)
    assert plays.num_rows > 0
    feed = {"gameData": {"status": {"abstractGameState": "Final"}},
            "liveData": {"plays": {"allPlays": json.loads(
                payload.read_text(encoding="utf-8"))}}}
    got = bu.workload_from_plays(feed["liveData"]["plays"]["allPlays"])
    want = _corpus_tally(plays, pitches)
    assert got == want
    # and through the stage-1 lab's own extraction of the same corpus rows
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "starter_workload_lab", ROOT / "tools" / "starter_workload_lab.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    games, _c = lab.games_from_tables(plays.to_pandas(), pitches.to_pandas(),
                                      {pk: day}, {pk: (home, away)}, 2025)
    g = games[0]
    for side, half in (("home", "top"), ("away", "bottom")):
        sp = g["starters"][half]
        assert got["sp"][side] == [sp, g["lines"][half][sp]["pitches"],
                                   g["lines"][half][sp]["outs"]]
    for side, half in (("home", "bottom"), ("away", "top")):
        assert got["bat"][side] == [g["batting"][half]["pitches"],
                                    g["batting"][half]["pa"]]


def test_parity_with_the_corpus_on_a_2026_game():
    pk, _day = PARITY_2026
    if not (FEEDS / f"{pk}.json").exists():
        pytest.skip("the 2026 feed cache is not on this box")
    plays, pitches = _corpus_game(2026, pk)
    assert plays.num_rows > 0
    t = bu.game_workload_tally(pk, FEEDS)
    assert t["complete"] is True and t["stamp"]
    assert {"sp": t["sp"], "bat": t["bat"]} == _corpus_tally(plays, pitches)


# ---------------------------------------------------------------------------
# 5. the basis stamp
# ---------------------------------------------------------------------------
def test_the_basis_carries_the_priors_anchors_counts_and_stamps(lg, tmp_path):
    out = _build(lg, tmp_path)
    b = out["basis"]
    assert b["status"] == "built" and b["priors"] == bu.SW_PRIORS
    assert b["window_pitcher"] == [_days(D, -365), D]
    assert b["window_club"] == [_days(D, -30), D]
    assert b["latest_feed_stamp"] == "20260101_000000"
    assert set(b["club_latest_feed_stamp"]) == {"NYY", "SEA", "BOS"}
    a = b["anchors"]
    raw_p = b["pitchers_raw"]["values"]
    assert b["pitchers_raw"]["fields"] == ["starts", "pitches", "outs"]
    assert set(raw_p) == {"11", "12", "21", "22", "31", "77"}
    # every value rebuilds from its raw counts and the anchors in the basis
    for mid, (n, pit, outs) in raw_p.items():
        assert out["sp_n365"]["values"][mid] == n
        bud = (pit + 2 * a["L_pgs"]) / (n + 2)
        ppo = (pit + 120 * a["L_ppo"]) / (outs + 120)
        assert out["sp_budget"]["values"][mid] == round(bud, 4)
        assert out["sp_ppo"]["values"][mid] == round(ppo, 5)
        assert out["sp_xouts"]["values"][mid] == round(min(27.0, bud / ppo), 4)
    for org, (pit, pa, _ng) in b["clubs_raw"]["values"].items():
        assert out["bat_ppa_l30"]["values"][org] == round(
            (pit + 300 * a["L_ppa"]) / (pa + 300), 5)
    for c in COLUMNS:
        assert "ABSENT" not in out[c]["basis"]
    assert "k_b 2, k_o 120, k_l 300" in out["sp_budget"]["basis"]


# ---------------------------------------------------------------------------
# 6. the seam in leaderboard_vintages, old records, inputs_as_of
# ---------------------------------------------------------------------------
def _boards(data: Path):
    orgs = ("NYY", "SEA", "BOS")
    (data / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-05-31",
        "teams": [{"team": o, "offense_plus": 100 + i} for i, o in enumerate(orgs)],
        "hitters": []}), encoding="utf-8")
    (data / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-05-31",
        "teams": [{"team": o, "rotation_plus": 100, "starter_ip": 500.0} for o in orgs],
        "starters": [{"mlbam": 11, "team": "NYY", "sem_plus": 120, "ip_per_gs": 5.5,
                      "role": "SP"}]}), encoding="utf-8")
    (data / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-05-31",
        "teams": [{"team": o, "bullpen_plus": 100, "relief_ip": 300.0} for o in orgs],
        "relievers": [{"mlbam": 77, "team": "SEA", "rem_plus": 104}]}), encoding="utf-8")


@pytest.fixture
def seam(lg, tmp_path, monkeypatch):
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand", lambda season: {})
    monkeypatch.setattr(bu, "build_schema4_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA4_TEAM_COLUMNS})
    monkeypatch.setattr(bu, "build_pitcher_schema4", lambda *a, **k: {})
    monkeypatch.setattr(bu, "build_schema5_team_columns",
                        lambda *a, **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                         for c in lv.SCHEMA5_PH_TALLY_COLUMNS})
    monkeypatch.setattr(bu, "FEED_DIR", lg.dir)
    monkeypatch.setattr(bu, "SW_ARTIFACT", _artifact(tmp_path))
    monkeypatch.setattr(bm, "completed_games", lambda *a, **k: list(lg.games))
    data = tmp_path / "data"
    data.mkdir()
    _boards(data)
    return data


def test_reduce_current_stores_the_columns_the_block_and_the_basis(seam, lg, tmp_path):
    rec = lv.reduce_current(on_date=D, data_dir=seam)
    assert rec["schema"] == lv.SCHEMA
    assert rec["pitcher_columns"][-4:] == list(PITCHER_COLS)
    assert rec["team_columns"][-1] == "bat_ppa_l30"
    assert all(len(r) == len(lv.PITCHER_COLUMNS) for r in rec["pitchers"].values())
    direct = _build(lg, tmp_path, pitchers=("11", "77"))
    for mid in ("11", "77"):
        row = lv.pitcher_row(rec, mid)
        for c in PITCHER_COLS:
            assert row[c] == direct[c]["values"][mid], (mid, c)
    for org in ("NYY", "SEA", "BOS"):
        assert lv.team_row(rec, org)["bat_ppa_l30"] == direct["bat_ppa_l30"]["values"][org]
    fb = rec["feature_basis"]
    assert fb["sp_n365"]["n"] == 2 and fb["bat_ppa_l30"]["n"] == 3
    blk = rec[lv.SW_BASIS_KEY]
    assert blk["status"] == "built" and blk["priors"] == bu.SW_PRIORS
    # the dark team column reaches the assembled inputs, standardized and unread
    teams = bm.team_inputs_from_vintage(rec)
    assert teams["NYY"]["bat_ppa_l30"] is not None
    assert "z_bat_ppa_l30" in teams["NYY"]


def test_a_builder_failure_costs_its_columns_a_stated_null(seam, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(bu, "build_schema7_workload_columns", boom)
    rec = lv.reduce_current(on_date=D, data_dir=seam)
    assert rec is not None
    for c in COLUMNS:
        assert rec["feature_basis"][c]["n"] == 0
        assert "RuntimeError: synthetic" in rec["feature_basis"][c]["basis"]
    assert rec[lv.SW_BASIS_KEY]["status"] == "unavailable"
    assert lv.pitcher_row(rec, 11)["sp_n365"] is None


def test_an_older_record_reads_none_and_says_it_predates_the_column():
    cols_t = [c for c in lv.TEAM_COLUMNS if c not in TEAM_COLS]
    cols_p = [c for c in lv.PITCHER_COLUMNS if c not in PITCHER_COLS]
    rec = {"schema": lv.SW_SCHEMA - 1, "team_columns": cols_t, "pitcher_columns": cols_p,
           "teams": {"NYY": [100.0] * len(cols_t)},
           "pitchers": {"11": [120.0, 5.5, "NYY", "SP", "R", 5, 3.1]},
           "feature_basis": {"park": {"basis": "fixture", "n": 0}}}
    assert all(lv.pitcher_row(rec, 11)[c] is None for c in PITCHER_COLS)
    assert lv.team_row(rec, "NYY")["bat_ppa_l30"] is None
    fb = lv.feature_basis(rec)
    for c in COLUMNS:
        assert fb[c]["n"] == 0
        assert f"(added in schema {lv.SW_SCHEMA}, {lv.SW_ADDED})" in fb[c]["basis"]
    teams = bm.team_inputs_from_vintage({**rec, "teams": {
        o: [100.0, 100.0, 100.0, 500.0, 300.0] + [None] * (len(cols_t) - 5)
        for o in ("NYY", "BOS")}})
    assert teams["NYY"]["bat_ppa_l30"] is None and teams["NYY"]["z_bat_ppa_l30"] is None


def test_inputs_as_of_never_fills_a_workload_column_from_live_files(tmp_path, monkeypatch):
    monkeypatch.setattr(lv, "VINTAGE_DIR", tmp_path / "empty")
    lv.reset_cache()
    bm._VINTAGE_CACHE.clear()
    try:
        live = bm.inputs_as_of("2026-06-01")
        assert live["source"] == "live-leaderboards"
        for k, r in live["teams"].items():
            if k.startswith("_"):
                continue
            assert r["bat_ppa_l30"] is None and r["z_bat_ppa_l30"] is None
        for r in (live.get("starters") or {}).values():
            for c in PITCHER_COLS:
                assert c not in r
    finally:
        lv.reset_cache()
        bm._VINTAGE_CACHE.clear()


# ---------------------------------------------------------------------------
# 7. the clock
# ---------------------------------------------------------------------------
def test_the_clock():
    """The builder lands after the section and before Opening Day 2027, on the date the
    store records as the columns' first night; nothing serves the candidate before its
    stage-2 look."""
    landed, _text = _landed()
    head = _section().splitlines()[0]
    reg = re.search(r"pre-registered (20\d\d-\d\d-\d\d)", head).group(1)
    assert reg <= landed < "2027-03-01"
    assert lv.SW_ADDED == landed
    for flag in ("SERVE_STARTER_WORKLOAD", "SERVE_WORKLOAD_PROPS"):
        assert not hasattr(bm, flag)


# ---------------------------------------------------------------------------
# 8. no served path reads a workload column, by AST and by string
# ---------------------------------------------------------------------------
#: The modules allowed to name a workload column or symbol: the store and the builder,
#: and betting_model's two DARK7 tuples (checked node by node below). The section's own
#: stage-2 look tool (tools/betting_workload_gate.py, the one registered reader, which
#: refuses before 2027-07-01 and is imported by no served module, pinned in
#: test_betting_workload_gate.py) reads the columns too.
ALLOWED = {"leaderboard_vintages.py", "betting_usage.py", "betting_workload_gate.py"}
NAMES = COLUMNS + ("sw_basis",)
SYMBOLS = ("SW_PITCHER_COLUMNS", "SW_TEAM_COLUMNS", "SW_BASIS_KEY", "SW_PRIORS",
           "build_schema7_workload_columns", "starter_workload_xouts_candidate",
           "workload_from_plays", "game_workload_tally", "sw_tallies", "sw_anchors",
           "sw_stage1_gate", "DARK7_TEAM_COLUMNS", "DARK7_PITCHER_COLUMNS")
DARK7 = ("DARK7_TEAM_COLUMNS", "DARK7_PITCHER_COLUMNS")


def _modules() -> list[Path]:
    out = []
    for base, pat in ((ROOT, "*.py"), (ROOT / "tools", "*.py"), (ROOT / "assets", "*.js")):
        for p in sorted(base.glob(pat)):
            if p.name.startswith("test_") or p.name == "conftest.py":
                continue
            out.append(p)
    return out


def _dark7_nodes(tree: ast.AST) -> set:
    nodes = set()
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in DARK7):
            nodes |= set(ast.walk(node))
    assert nodes, "betting_model has no DARK7 tuples"
    return nodes


def test_no_served_path_reads_a_workload_column_by_ast():
    offenders = []
    for p in _modules():
        if p.suffix != ".py" or p.name in ALLOWED:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        inside = _dark7_nodes(tree) if p.name == "betting_model.py" else set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in NAMES and node not in inside):
                offenders.append(f"{p.name}:{node.lineno} {node.value!r}")
            if isinstance(node, ast.Attribute) and node.attr in SYMBOLS:
                offenders.append(f"{p.name}:{node.lineno} .{node.attr}")
            if (isinstance(node, ast.Name) and node.id in SYMBOLS
                    and not (p.name == "betting_model.py" and node.id in DARK7)):
                offenders.append(f"{p.name}:{node.lineno} {node.id}")
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "betting_usage":
                hit = [a.name for a in node.names if a.name in SYMBOLS]
                if hit:
                    offenders.append(f"{p.name}:{node.lineno} imports {hit}")
        if p.name == "betting_model.py":
            for sym in DARK7:
                uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                        and n.id == sym]
                want = 3 if sym == "DARK7_TEAM_COLUMNS" else 1
                assert len(uses) == want, (
                    f"{sym} is defined and enters only the two team DARK maps "
                    f"(the pitcher tuple is defined only); found {len(uses)} uses")
    assert not offenders, offenders


def test_no_served_path_names_a_workload_column_by_string():
    offenders = []
    for p in _modules():
        if p.name in ALLOWED:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if p.name == "betting_model.py":
            tree = ast.parse(src)
            for node in tree.body:
                if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in DARK7):
                    src = src.replace(ast.get_source_segment(src, node), "")
        for name in NAMES:
            if re.search(r"\b" + name + r"\b", src):
                offenders.append(f"{p.relative_to(ROOT).as_posix()} names {name}")
    assert not offenders, offenders


def test_only_the_store_calls_the_builder_and_nothing_calls_the_candidate():
    tree = ast.parse((ROOT / "leaderboard_vintages.py").read_text(encoding="utf-8"))
    calls = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and isinstance(n.value, ast.Name) and n.value.id == "betting_usage"
             and n.attr in SYMBOLS]
    assert calls == ["build_schema7_workload_columns"]
    src = (ROOT / "betting_usage.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id == "starter_workload_xouts_candidate"]
    assert not called, "the candidate function is called inside betting_usage"
    # the builder reads no result: no runs or score key appears in its source
    seg = "\n".join(ast.get_source_segment(src, n) for n in tree.body
                    if isinstance(n, ast.FunctionDef)
                    and n.name in ("workload_from_plays", "game_workload_tally",
                                   "sw_tallies", "sw_anchors",
                                   "build_schema7_workload_columns",
                                   "starter_workload_xouts_candidate"))
    for key in ("home_runs", "away_runs", "homeScore", "awayScore", "linescore",
                "isScoringPlay", "rbi"):
        assert key not in seg, key
