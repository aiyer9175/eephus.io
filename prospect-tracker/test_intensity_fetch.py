"""tools/intensity_fetch.py: the game-intensity study's fetches (section 5o, item H2).

Pins: the fetcher refuses to write under data/ and under .cache/win_prob/; postseason
feeds land in .cache/win_prob_post/, wrapped with their game type, which the play-corpus
builder's default glob never sees; requests are spaced and identified; the game lists
and receipts carry no score field; and, where the fetched finals are on this machine,
each season's count reconciles to the corpus census (2,429 to 2,431 games a season).
Hermetic except the census test, which skips on a box without the cache.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import build_pbp_corpus as bpc  # noqa: E402
import intensity_fetch as itf  # noqa: E402

TOOL = ROOT / "tools" / "intensity_fetch.py"


class _Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.payload


class _Get:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        return _Resp(self.payload)


def _pacer():
    return itf.Pacer(gap=0.0, sleep=lambda s: None)


GAME = {"game_pk": 123456, "season": 2019, "game_type": "W", "official_date": "2019-10-30"}
PLAYS = [{"about": {"startTime": "2019-10-31T00:08:00Z"}, "homeTeamWinProbability": 50.0},
         {"about": {"startTime": "2019-10-31T03:20:00Z"}, "homeTeamWinProbability": 100.0}]


# ---------------------------------------------------------------------------
# where it may write
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel", ["data/x.json", "data/_labs/y.json", "data",
                                 ".cache/win_prob/1.json", ".cache/win_prob",
                                 ".cache/win_prob/sub/2.json"])
def test_the_fetcher_refuses_data_and_the_regular_season_feed_cache(rel):
    with pytest.raises(itf.FetchRefused):
        itf.check_target(ROOT / rel)


def test_the_postseason_feed_dir_is_its_own_sibling_and_allowed():
    assert itf.FEED_DIR.name == "win_prob_post"
    assert itf.FEED_DIR.parent == bpc.DEFAULT_CACHE.parent
    assert not itf.FEED_DIR.is_relative_to(bpc.DEFAULT_CACHE)
    itf.check_target(itf.FEED_DIR / "1.json")
    itf.check_target(itf.FINALS_DIR / "2018.json")


def test_a_feed_aimed_at_win_prob_is_refused_before_any_request():
    get = _Get({"winProbability": PLAYS})
    with pytest.raises(itf.FetchRefused):
        itf.fetch_feed(GAME, pacer=_pacer(), get=get, feed_dir=ROOT / ".cache" / "win_prob")
    with pytest.raises(itf.FetchRefused):
        itf.fetch_feed(GAME, pacer=_pacer(), get=get, feed_dir=ROOT / "data")
    assert get.calls == []


def test_finals_aimed_at_data_are_refused_before_any_request():
    calls = []
    with pytest.raises(itf.FetchRefused):
        itf.fetch_regular_season(2018, pacer=_pacer(), fetch=lambda a, b: calls.append(a) or [],
                                 finals_dir=ROOT / "data" / "regular_finals")
    assert calls == []


def test_the_receipt_cannot_go_under_data(tmp_path):
    with pytest.raises(itf.FetchRefused):
        itf._write_json(ROOT / "data" / "intensity_fetch_receipt.json", {})


def test_the_corpus_builder_default_glob_never_sees_win_prob_post(tmp_path):
    """The builder indexes its cache dir with a flat *.json glob; a feed in the sibling
    win_prob_post directory is not in that index."""
    reg, post = tmp_path / "win_prob", tmp_path / "win_prob_post"
    reg.mkdir()
    post.mkdir()
    (reg / "111.json").write_text(json.dumps(PLAYS), encoding="utf-8")
    itf.fetch_feed(GAME, pacer=_pacer(), get=_Get({"winProbability": PLAYS}), feed_dir=post)
    assert (post / "123456.json").exists()
    seen = [p.name for v in bpc.index_by_season(reg).values() for p in v]
    assert seen == ["111.json"]
    assert bpc.DEFAULT_CACHE.name == "win_prob"
    src = (ROOT / "tools" / "build_pbp_corpus.py").read_text(encoding="utf-8")
    assert "win_prob_post" not in src and "rglob" not in src


# ---------------------------------------------------------------------------
# the feed file, the pacing, the identity
# ---------------------------------------------------------------------------
def test_a_postseason_feed_is_wrapped_with_its_game_type(tmp_path):
    get = _Get({"winProbability": PLAYS})
    r = itf.fetch_feed(GAME, pacer=_pacer(), get=get, feed_dir=tmp_path)
    assert get.calls == [itf.WP_URL.format(pk=123456)]
    doc = json.loads((tmp_path / "123456.json").read_text(encoding="utf-8"))
    assert doc["game_type"] == "W" and doc["season"] == 2019 and doc["plays"] == PLAYS
    assert not isinstance(doc, list)
    assert r["status"] == "complete" and r["n_plays"] == 2 and r["cached"] is False
    again = itf.fetch_feed(GAME, pacer=_pacer(), get=get, feed_dir=tmp_path)
    assert again["cached"] is True and len(get.calls) == 1


def test_a_failed_request_is_a_counted_error_not_an_abort(tmp_path):
    def boom(url, timeout=None):
        raise ConnectionError("down")
    r = itf.fetch_feed(GAME, pacer=_pacer(), get=boom, feed_dir=tmp_path)
    assert r["status"] == "error" and not (tmp_path / "123456.json").exists()


def test_requests_are_spaced_and_identified():
    t = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        t[0] += s
    p = itf.Pacer(clock=lambda: t[0], sleep=sleep)
    p.wait()
    t[0] += 0.3
    p.wait()
    p.wait()
    assert itf.MIN_GAP_S >= 1.1
    assert slept and all(abs(s - v) < 1e-9 for s, v in zip(slept, [0.8, 1.1]))
    assert "eephus.io" in itf.USER_AGENT and "intensity" in itf.USER_AGENT


# ---------------------------------------------------------------------------
# lists, counts, no score
# ---------------------------------------------------------------------------
def _g(pk, gt, code="F", date="2019-10-01"):
    return {"gamePk": pk, "gameType": gt, "officialDate": date, "status": {"codedGameState": code},
            "teams": {"home": {"team": {"id": 1}, "score": 9, "isWinner": True},
                      "away": {"team": {"id": 2}, "score": 1, "isWinner": False}}}


def test_the_postseason_list_keeps_final_postseason_games_once_and_no_score():
    body = {"series": [{"series": {"gameType": "D"},
                        "games": [_g(1, "D"), _g(2, "D", code="C"), _g(1, "D")]},
                       {"series": {"gameType": "R"}, "games": [_g(3, "R")]},
                       {"series": {"gameType": "W"}, "games": [_g(4, "W", code="O")]}]}
    games, drops = itf.postseason_games_from_body(body, 2019)
    assert [g["game_pk"] for g in games] == [1, 4]
    assert drops == {"not_final": 1, "duplicate_game_pk": 1, "game_type_R": 1}
    for g in games:
        assert set(g) == {"game_pk", "season", "game_type", "official_date"}


def test_regular_rows_keep_the_season_once():
    rows = [{"game_pk": 1, "season": "2018", "date": "2018-05-01"},
            {"game_pk": 1, "season": "2018", "date": "2018-06-12"},
            {"game_pk": 2, "season": "2019"}, {"game_pk": 3, "season": "2018", "game_type": "D"},
            {"game_pk": 4, "season": "2018", "date": "2018-07-01"}]
    kept, drops, multi = itf.keep_regular_rows(rows, 2018)
    assert [r["game_pk"] for r in kept] == [1, 4] and kept[0]["date"] == "2018-05-01"
    assert drops == {"duplicate_game_pk": 1, "season_not_requested": 1, "not_regular_season": 1}
    assert multi == {"1": ["2018-05-01", "2018-06-12"]}


def test_reconcile_compares_game_pk_lists_only():
    r = itf.reconcile(2018, range(1, 2432), set(range(2, 2433)))
    assert r["n_finals"] == 2431 and r["census"] == 2431 and r["in_census_range"]
    assert r["only_in_finals"] == [1] and r["only_in_corpus"] == [2432]
    assert not itf.reconcile(2019, range(2000), None)["in_census_range"]


def test_the_tool_reads_no_score_field():
    """No score, winner or price key is read anywhere in the tool's code."""
    code = TOOL.read_text(encoding="utf-8")
    for key in ("home_runs", "away_runs", "isWinner", "linescore", "homeTeamWinProbabilityAdded",
                "the-odds-api"):
        assert key not in code, key
    for key in ("score", "runs", "winner", "price", "odds", "stake"):
        assert not re.search(r"""\[\s*["']""" + key + r"""["']\s*\]|\.get\(\s*["']""" + key
                             + r"""["']""", code), key


def test_2020_is_refused():
    with pytest.raises(SystemExit):
        itf.main(["--regular", "2020", "--postseasons", "", "--dry-run"])
    assert 2020 not in itf.REGULAR_SEASONS and 2020 not in itf.POSTSEASONS
    assert itf.POSTSEASONS_INT_B1 == tuple(range(2000, 2018))


# ---------------------------------------------------------------------------
# the census (data test; skips without the fetched cache)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("season", itf.REGULAR_SEASONS)
def test_the_fetched_finals_reconcile_to_the_corpus_census(season):
    doc = itf._read_json(itf.FINALS_DIR / f"{season}.json")
    if not isinstance(doc, dict):
        pytest.skip(f"no fetched {season} finals on this machine")
    pks = {int(r["game_pk"]) for r in doc["rows"]}
    assert len(pks) == doc["n_kept"] == len(doc["rows"])
    assert itf.CENSUS_LO <= len(pks) <= itf.CENSUS_HI, (season, len(pks))
