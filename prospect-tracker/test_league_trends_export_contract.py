# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""League Trends' payload contract (plan 4.3 to 4.5, 5.2 and 5.4; task
TR_3_EXPORT_PIPELINE_DARK).

Two halves. The ARTIFACT half reads the payload league_trends.json where the
flag puts it (.cache/league_trends/preview/ while
league_trends_export.MLBSTATS_TRENDS_LIVE is False, data/ after the flip) and
skips when none is on this machine: plan 5.2's keys, as_of equal to
covers_through and a game date not after generated_at, the coverage keys
bannerHTML reads, false_per_day equal to the tail times the tests, every
number in a sentence a field, the pitches per PA and starter innings cards
holding no live-season value, no series_ref on the stolen-base card, and the
60 KB raw budget. The FIXTURE half always runs on a synthetic frame
(test_trend_frames' fixture games): the stale frame refuses and keeps the last
good file, the off-season does not refuse, a missing eval artifact, a bar that
differs from the artifact and club identity under the floor refuse, a failed
live check and a missing swing season leave families off without refusing,
nothing is written under data/ while the flag is False, and the run_monthly
wiring is pinned by its step TITLES, never a letter. The eval artifact
league_trends_eval.json is the lab's (test_league_trends_eval.py); here only
its live-check refresh is pinned: it never changes a bar.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import league_trends_export as X
import test_trend_frames as TTF
import trend_detect as TD
import trend_frames as TF

ROOT = Path(__file__).resolve().parent
NL = chr(10)
POL = TD.BAR_POLICY
PAYLOAD = X.out_dir() / X.OUT_NAME
FIXTURE_SEASON = TTF.FRAME_SEASON


# --------------------------------------------------------------------------- #
# the served artifact (skips when none is on this machine)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def doc():
    if not PAYLOAD.exists():
        pytest.skip(f"no League Trends payload on this machine ({PAYLOAD}); "
                    "run python league_trends_export.py")
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_payload_path_follows_the_flag():
    assert X.out_dir() == (X.DATA_DIR if X.MLBSTATS_TRENDS_LIVE else X.PREVIEW_DIR)
    assert X.eval_path().parent == X.out_dir()
    if not X.MLBSTATS_TRENDS_LIVE:
        assert ".cache" in X.out_dir().parts and "preview" in X.out_dir().parts
        assert not (X.DATA_DIR / X.OUT_NAME).exists(), "nothing under data/ while dark"
        assert not (X.DATA_DIR / X.EVAL_NAME).exists(), "nothing under data/ while dark"


def test_top_level_keys_plan_5_2(doc):
    for k in ("schema", "generated_at", "season", "mode", "as_of", "covers_through",
              "coverage", "verdict", "method", "families", "players", "events", "teams",
              "league", "left_off", "swing_missing"):
        assert k in doc, k
    assert doc["verdict"] == "descriptive"
    assert doc["flag"] == {"MLBSTATS_TRENDS_LIVE": X.MLBSTATS_TRENDS_LIVE}
    for k in ("fold", "false_per_day", "eval"):
        assert k in doc["method"], k
    assert doc["method"]["eval"] == f"data/{X.EVAL_NAME}"


def test_as_of_is_covers_through_and_a_game_date_not_after_generated_at(doc):
    assert doc["as_of"] == doc["covers_through"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["as_of"])
    gen = datetime.strptime(doc["generated_at"], "%Y-%m-%dT%H:%M:%SZ")
    assert doc["as_of"] <= gen.date().isoformat()
    assert int(doc["as_of"][:4]) == doc["season"]
    if doc.get("boards_last_game"):
        assert doc["as_of"] <= doc["boards_last_game"] or \
            X.stale_reason(doc["as_of"], doc["boards_last_game"]) is None


def test_coverage_keys_banner_reads(doc):
    """assets/mlbstats.js bannerHTML reads season, as_of, coverage.games,
    coverage.expected and verdict."""
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    body = js[js.index("function bannerHTML"):]
    body = body[:body.index("function banner()")]
    for key in ("d.season", "d.as_of", "d.coverage", "cov.games", "cov.expected", "d.verdict"):
        assert key in body, key
    assert isinstance(doc["coverage"]["games"], int) and doc["coverage"]["games"] > 0
    assert isinstance(doc["coverage"]["expected"], int)
    assert doc["coverage"]["games"] <= doc["coverage"]["expected"]


def test_false_per_day_is_tail_times_tests_and_the_method_is_their_sum(doc):
    tot = 0.0
    for f in doc["families"]:
        for k in ("tail_per_test", "tests_today", "false_per_day", "pooled_flags", "bar"):
            assert k in f, (f["key"], k)
        assert f["false_per_day"] == pytest.approx(round(f["tail_per_test"] * f["tests_today"], 4),
                                                   abs=1e-9), f["key"]
        assert f["bar"] == float(TD.bar_for(f["key"]))
        tot += f["false_per_day"]
        if f.get("prior"):
            p = f["prior"]
            assert p["false_per_day"] == pytest.approx(
                round(p["tail_per_test"] * p["tests_today"], 4), abs=1e-9)
            tot += p["false_per_day"]
        if TD.FAMILIES[f["key"]].kind == "swing":
            assert f["pool"] and f["as_of"] and f["as_of"] <= doc["as_of"]
    assert doc["method"]["false_per_day"] == pytest.approx(round(tot, 3), abs=1e-9)
    assert f"{doc['method']['false_per_day']:.2f}" in doc["method"]["fold"]
    if doc["method"].get("one_in"):
        assert f"1 listed change in {doc['method']['one_in']} " in doc["method"]["fold"]


def _numbers(s: str) -> list:
    return re.findall(r"\d+(?:\.\d+)?", s)


def _field_strings(obj, skip=("spark", "context", "links", "sentence", "id")) -> set:
    out: set = set()

    def walk(o, key=None):
        if key in skip:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
        elif isinstance(o, bool) or o is None:
            return
        elif isinstance(o, (int, float)):
            for nd in range(0, 4):
                out.add(f"{abs(float(o)):.{nd}f}")
            if float(o).is_integer():
                out.add(str(abs(int(o))))
    walk(obj)
    return out


def test_every_number_in_a_sentence_is_a_field(doc):
    in_season = doc["mode"] == "in_season"
    for c in doc["players"]:
        assert c["sentence"] == X.card_sentence(c), c["id"]
        allowed = _field_strings(c)
        for n in _numbers(c["sentence"]):
            assert n in allowed, (c["id"], n, c["sentence"])
    for e in doc["events"]:
        assert e["sentence"] == X.event_sentence(e), e["id"]
        allowed = _field_strings(e)
        for n in _numbers(e["sentence"]):
            assert n in allowed, (e["id"], n, e["sentence"])
    for c in doc["league"]:
        assert c["sentence"] == X.league_sentence(c, in_season), c["key"]
        allowed = _field_strings(c, skip=("values", "sentence", "footnote"))
        for n in _numbers(c["sentence"]):
            assert n in allowed, (c["key"], n, c["sentence"])
    for t in doc["teams"]:
        if t.get("sentence"):
            assert t["sentence"] == X.team_sentence(t)


def test_player_cards_plan_5_2(doc):
    fams = {f["key"]: f for f in doc["families"]}
    for c in doc["players"]:
        assert c["family"] in fams and c["family"] in TD.FAMILIES
        sp = c["spark"]
        assert 1 <= len(sp["v"]) <= X.SPARK_N == 20
        assert 0 <= sp["w"] <= len(sp["v"])
        ctx = c["context"]
        if c["role"] == "H":
            assert "obp_30d" in ctx and "k_bb_30d" not in ctx
        else:
            assert "k_bb_30d" in ctx and "obp_30d" not in ctx
        assert ctx["index"]["label"] in ("HEM+", "SEM+", "REM+")
        assert "woba" not in json.dumps(ctx).lower()
        assert c["first_flagged"] <= doc["as_of"] and c["window"]["to"] <= doc["as_of"]
        if c["family"] == "mix":
            assert "shrunk" in c


def test_completed_seasons_only_cards_hold_no_live_value(doc):
    by = {c["key"]: c for c in doc["league"]}
    for key in X.COMPLETED_ONLY:
        if key not in by:
            continue
        c = by[key]
        assert c["complete"] is True and c["completed_only"] is True
        assert c["season"] < doc["season"] or doc["mode"] == "final" and c["complete"]
        assert "Disqualification paragraph" in c["footnote"] and "section 5m" in c["footnote"]
        assert "values" not in c and "so far" not in c["sentence"]
    assert "ip_per_gs" not in by, "never ip_per_gs in place of sp_ip_per_gs"
    if "sp_ip_per_gs" in by:
        assert by["sp_ip_per_gs"]["series_ref"].endswith("#pit/sp_ip_per_gs")


def test_own_cards_carry_no_series_ref(doc):
    by = {c["key"]: c for c in doc["league"]}
    assert "sba_per_club_game" in by
    for key, *_rest in X.OWN_CARDS:
        if key in by:
            assert "series_ref" not in by[key], key
            assert by[key]["values"]
    for key, _l, side, skey, *_r in X.SERIES_CARDS:
        if key in by:
            assert by[key]["series_ref"] == f"{X.SERIES_NAME}#{side}/{skey}"


def test_size_within_budget(doc):
    raw = PAYLOAD.read_bytes()
    assert len(raw) <= X.BUDGET_RAW == 60_000


# --------------------------------------------------------------------------- #
# the fixture half
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def frame(tmp_path_factory):
    """test_trend_frames' fixture games through the real frame builder:
    20 games, 2025-05-01 to 2025-05-20."""
    from tools import build_pitch_physics as B
    tmp = tmp_path_factory.mktemp("lt_frame")
    wp = tmp / "win_prob"
    wp.mkdir()
    games = []
    for i in range(20):
        pk, plays = TTF._fx_game(i)
        (wp / f"{pk}.json").write_text(json.dumps(plays), encoding="utf-8")
        games.append((i, pk))
    phys = tmp / "phys"
    B.build(win_prob_dir=wp, out_dir=phys, live_season=FIXTURE_SEASON + 1)
    war = tmp / "bat.parquet"
    rows = [(b, FIXTURE_SEASON, "AAA", 500) for b in TTF.CLUB_A["bats"]] + \
           [(b, FIXTURE_SEASON, "BBB", 500) for b in TTF.CLUB_B["bats"]]
    pd.DataFrame(rows, columns=["mlb_ID", "year_ID", "team_ID", "PA"]).to_parquet(war, index=False)
    empty = tmp / "empty_corpus"
    empty.mkdir()
    days = TTF._fx_day_files(tmp / "savant_days", FIXTURE_SEASON, games)
    TTF._fx_day_files(days, FIXTURE_SEASON - 1, [(i, 980000 + i) for i in range(5)])
    return TF.pitch_game_frame(FIXTURE_SEASON, swing_dir=days, physics_dir=phys, war_daily=war,
                               corpus_dir=empty, win_prob_dir=wp,
                               games_memo_dir=tmp / "games_memo", memo_dir=tmp / "frame_memo",
                               receipts={})


def _art(served=None, **over) -> dict:
    bars = dict(TD.BARS[POL])
    served = sorted(bars) if served is None else served
    art = {
        "generated_at": "2026-10-01T00:00:00Z",
        "bars": {POL: bars},
        "placebo_sd": {k: TD.PLACEBO_SD[k] for k in bars},
        "served": served,
        "families": {k: {"chosen": {POL: {"bar": v, "tail_per_test": 1.5e-4, "flag_count": 40,
                                          "real": 0.96}}} for k, v in bars.items()},
        "totals": {POL: {"real": 0.97}},
        "shrink": {"seasons": {"pitch": [2023, 2024, 2025], "swing": [2024, 2025]}, "fits": {}},
        "mix_null": None,
        "prior_season": {"swing_ok": {}, "families": {}},
        "pool": {"label": "all tracked"},
        "rd_band": None, "rd_band_note": "null: fixture",
        "league_env": {"seasons": {str(y): {"sba_per_club_game": 0.6 + 0.05 * i,
                                            "ff_mph": 93.0 + 0.2 * i, "st_pct": 1.0 + i,
                                            "fs_pct": 1.5 + 0.1 * i}
                                   for i, y in enumerate((2018, 2019, 2021, 2022, 2023, 2024))}},
        "live_check": {"families": {}},
    }
    art.update(over)
    return art


def _series() -> dict:
    seasons = {}
    for i, y in enumerate(range(2018, FIXTURE_SEASON + 1)):
        seasons[str(y)] = {"complete": y < FIXTURE_SEASON, "games_per_team": 162,
                           "hit": {"all": {"k_pct": 0.20 + 0.003 * i, "bb_pct": 0.08,
                                           "hr_pct": 0.03, "p_per_pa": 3.85 + 0.01 * i}},
                           "pit": {"all": {"sp_ip_per_gs": 5.6 - 0.05 * i, "ip_per_gs": 5.5}}}
    return {"stats": {"hit": [{"key": k} for k in ("k_pct", "bb_pct", "hr_pct", "p_per_pa")],
                      "pit": [{"key": "sp_ip_per_gs"}, {"key": "ip_per_gs"}]},
            "seasons": seasons}


def _dates(last: str) -> list:
    out, d = [], pd.Timestamp(f"{FIXTURE_SEASON}-05-01")
    while d.date().isoformat() <= last:
        out.append(d.date().isoformat())
        d += pd.Timedelta(days=1)
    return out


def _kw(frame, **over) -> dict:
    kw = dict(art=_art(), frame=frame, prior=None,
              boards={"season": FIXTURE_SEASON, "as_of": f"{FIXTURE_SEASON}-05-21", "rows": {}},
              game_dates=_dates(f"{FIXTURE_SEASON}-05-20"), series=_series(), pal={},
              live_env={str(FIXTURE_SEASON): {"sba_per_club_game": 0.9, "ff_mph": 94.5,
                                              "st_pct": 8.0, "fs_pct": 3.0}},
              today=f"{FIXTURE_SEASON}-05-21", log=lambda *a, **k: None)
    kw.update(over)
    return kw


def _keys(o, out=None) -> set:
    out = set() if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(str(k))
            _keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _keys(v, out)
    return out


def test_fixture_build_is_the_contract(frame):
    doc = X.build(**_kw(frame))
    assert doc["as_of"] == doc["covers_through"] == f"{FIXTURE_SEASON}-05-20"
    assert doc["coverage"] == {"games": 20, "expected": 2430}
    assert doc["mode"] == "in_season" and doc["verdict"] == "descriptive"
    assert {f["key"] for f in doc["families"]} == set(TD.BARS[POL])
    for f in doc["families"]:
        assert f["false_per_day"] == round(f["tail_per_test"] * f["tests_today"], 4)
    assert doc["teams"] == [] and doc["teams_note"] == X.TEAMS_NOTE
    by = {c["key"]: c for c in doc["league"]}
    # completed seasons only: the live fixture season is never shown on these two
    for key in ("p_per_pa", "sp_ip_per_gs"):
        assert by[key]["season"] == FIXTURE_SEASON - 1 and by[key]["complete"]
        assert "section 5m" in by[key]["footnote"]
    assert by["k_rate"]["season"] == FIXTURE_SEASON and not by["k_rate"]["complete"]
    assert "so far" in by["k_rate"]["sentence"] and not by["k_rate"]["notable"]
    assert "series_ref" not in by["sba_per_club_game"]
    assert by["sba_per_club_game"]["values"][str(FIXTURE_SEASON)] == 0.9
    assert "ip_per_gs" not in by
    raw = X.encode(doc)
    assert len(raw) <= X.BUDGET_RAW


def test_sp_ip_per_gs_card_is_omitted_without_its_key(frame):
    s = _series()
    s["stats"]["pit"] = [{"key": "ip_per_gs"}]
    doc = X.build(**_kw(frame, series=s))
    keys = {c["key"] for c in doc["league"]}
    assert "sp_ip_per_gs" not in keys and "ip_per_gs" not in keys


def test_no_per_hand_grade_price_or_outcome_key(frame):
    doc = X.build(**_kw(frame))
    banned = re.compile(r"(^|_)(vs_?[lr]|lhp|rhp|lhh|rhh|hand|platoon|grade|fv|price|odds|"
                        r"moneyline|outcome|result|win_prob|wpa)($|_)", re.I)
    bad = sorted(k for k in _keys(doc) if banned.search(k))
    assert not bad, bad
    if PAYLOAD.exists():
        bad = sorted(k for k in _keys(json.loads(PAYLOAD.read_text(encoding="utf-8")))
                     if banned.search(k))
        assert not bad, bad


def test_the_stale_fixture_refuses_and_keeps_the_last_good_file(frame, tmp_path):
    """A frame 5 days behind the boards' last game date refuses."""
    out = tmp_path / "league_trends.json"
    out.write_bytes(b"last good")
    kw = _kw(frame, boards={"season": FIXTURE_SEASON, "as_of": f"{FIXTURE_SEASON}-05-27",
                            "rows": {}},
             game_dates=_dates(f"{FIXTURE_SEASON}-05-25"))
    res = X.export(out=out, **kw)
    assert res["refused"] and "5 days before" in res["refused"] and not res["written"]
    assert out.read_bytes() == b"last good"
    assert X.stale_reason("2026-09-22", "2026-09-27") is not None


def test_the_off_season_fixture_does_not_refuse(frame, tmp_path):
    """Boards built 2026-11-15, last game 2026-09-27, frame through 09-27: game
    dates, never build stamps."""
    dates = [f"2026-09-{d:02d}" for d in range(1, 28)]
    last = X.boards_last_game_date("2026-11-15", dates)
    assert last == "2026-09-27"
    assert X.stale_reason("2026-09-27", last) is None
    # the same on the fixture frame: boards built months after its last game
    kw = _kw(frame, boards={"season": FIXTURE_SEASON, "as_of": f"{FIXTURE_SEASON}-11-15",
                            "rows": {}}, today=f"{FIXTURE_SEASON}-11-15")
    res = X.export(out=tmp_path / "lt.json", **kw)
    assert res["refused"] is None and res["as_of"] == f"{FIXTURE_SEASON}-05-20"


def test_a_missing_eval_artifact_refuses(frame, tmp_path, monkeypatch):
    monkeypatch.setattr(X, "eval_path", lambda: tmp_path / "absent.json")
    res = X.export(out=tmp_path / "lt.json", **_kw(frame, art=None))
    assert res["refused"] and "no eval artifact" in res["refused"]
    assert not (tmp_path / "lt.json").exists()


def test_a_bar_that_differs_from_the_artifact_refuses(frame, tmp_path):
    art = _art()
    k = sorted(art["bars"][POL])[0]
    art["bars"][POL][k] = float(art["bars"][POL][k]) + 0.25
    res = X.export(out=tmp_path / "lt.json", **_kw(frame, art=art))
    assert res["refused"] and "differ from the eval artifact" in res["refused"]
    art = _art()
    art["placebo_sd"][k] = 1.5
    assert "placebo SD" in X.export(out=tmp_path / "lt.json", **_kw(frame, art=art))["refused"]


def test_club_identity_under_the_floor_refuses(tmp_path, monkeypatch):
    def under(*_a, **_k):
        raise ValueError("resolved share 0.80 below the floor 0.95")
    monkeypatch.setattr(TF, "pitch_game_frame", under)
    res = X.export(out=tmp_path / "lt.json", **_kw(None))
    assert res["refused"] and "below the floor" in res["refused"]


def test_a_failed_live_check_leaves_the_family_off_without_refusing(frame):
    art = _art(live_check={"families": {"rp_velo": "left off", "sp_velo": "kept"}})
    doc = X.build(**_kw(frame, art=art))
    assert "rp_velo" not in {f["key"] for f in doc["families"]}
    assert [f["key"] for f in doc["left_off"]] == ["rp_velo"]


def test_a_missing_swing_season_leaves_the_swing_families_off(frame, monkeypatch):
    calls = []

    def fake(season, **k):
        calls.append(k.get("with_swings", True))
        if k.get("with_swings", True):
            raise TF.SwingSeasonsMissing([season - 1], "savant_days", {season - 1: "(pruned)"})
        return frame
    monkeypatch.setattr(TF, "pitch_game_frame", fake)
    doc = X.build(**_kw(None, prior=None))
    swing = {k for k, f in TD.FAMILIES.items() if f.kind == "swing"} & set(TD.BARS[POL])
    assert swing and not swing & {f["key"] for f in doc["families"]}
    assert swing <= {f["key"] for f in doc["left_off"]}
    assert doc["swing_missing"] == {str(FIXTURE_SEASON - 1): "(pruned)"}
    assert calls[:2] == [True, False]


def test_a_stale_swing_source_in_season_leaves_the_swing_families_off(frame):
    meta = dict(frame.meta, swing=dict(frame.meta["swing"], as_of=f"{FIXTURE_SEASON}-05-10"))
    doc = X.build(**_kw(frame._replace(meta=meta)))
    swing = {k for k, f in TD.FAMILIES.items() if f.kind == "swing"} & set(TD.BARS[POL])
    off = {f["key"]: f["reason"] for f in doc["left_off"]}
    assert swing <= set(off) and all("trails" in off[k] for k in swing)
    # a swing family that is listed carries D_swing as its own as_of
    meta = dict(frame.meta, swing=dict(frame.meta["swing"], as_of=f"{FIXTURE_SEASON}-05-18"))
    doc = X.build(**_kw(frame._replace(meta=meta)))
    for f in doc["families"]:
        if f["key"] in swing:
            assert f["as_of"] == f"{FIXTURE_SEASON}-05-18" and f["pool"] == "all tracked"


def test_teams_are_built_from_rd_band_and_counts_only(frame):
    doc = X.build(**_kw(frame, art=_art(rd_band={"sigma_m": 4.4, "seasons": [2021, 2025]})))
    assert [t["club"] for t in doc["teams"]] == ["AAA", "BBB"]
    for t in doc["teams"]:
        assert t["rd"]["l10"]["n"] == 10 and t["rd"]["before_l10"]["n"] == 10
        assert t["rd"]["band_l10"] == round(4.4 * (1 / 10 + 1 / 10) ** 0.5, 1)
        assert t["rd"]["band_l30"] is None          # 20 games: no earlier games for 30
        assert set(t["pen"]) >= {"relief_outs_3d", "relief_pitches_7d"}
        assert t["sentence"] == X.team_sentence(t)
    assert X.build(**_kw(frame))["teams"] == []


def test_nothing_under_data_while_the_flag_is_false(frame, tmp_path, monkeypatch):
    data, prev = tmp_path / "data", tmp_path / "preview"
    data.mkdir()
    monkeypatch.setattr(X, "DATA_DIR", data)
    monkeypatch.setattr(X, "PREVIEW_DIR", prev)
    monkeypatch.setattr(X, "MLBSTATS_TRENDS_LIVE", False)
    res = X.export(**_kw(frame))
    assert res["refused"] is None and Path(res["out"]) == prev / X.OUT_NAME
    assert (prev / X.OUT_NAME).exists() and not any(data.iterdir())


def test_an_oversize_payload_refuses(frame, tmp_path, monkeypatch):
    out = tmp_path / "lt.json"
    out.write_bytes(b"last good")
    monkeypatch.setattr(X, "BUDGET_RAW", 100)
    res = X.export(out=out, **_kw(frame))
    assert res["refused"] and "budget" in res["refused"] and out.read_bytes() == b"last good"
