# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""F-SCORE, the seven-season franchise score (fscore_export.py), built dark.

Every identity of fscore.md 2.12 as the plan amends it, on fixtures: the score
is 100 + 10z with ranks and letters that agree; the weights, the recency and
the ladder are the owner's answers and equal the payload; RESULTS season
values sum to zero; the roster and outlook legs equal the Franchise branch
scores; OPERATIONS goes dark on the DECLARED vector, never pro rata; no key is
grouped by a grade and no management value enters. The refusals (a missing
club, a missing completed season, a broken bracket) leave nothing written. The
nightly order pins the Teams payload after F-SCORE (orchestrator ruling X13).
The real-data build is checked only where its caches are on disk.
"""
from __future__ import annotations

import copy as _copy
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import fscore_export as FX  # noqa: E402
import franchise_export as FE  # noqa: E402

NL = chr(10)
SEASONS = list(range(2020, 2027))
CODES = ["ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
         "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
         "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN"]
#: Wins above 81 by club position: symmetric, so every season's W and L balance.
D = list(range(-15, 0)) + list(range(1, 16))


def _bracket(season: int, complete: bool = True) -> dict:
    """A twelve-club bracket (eight in 2020 style counts are not needed here):
    one champion, one World Series loser, two LCS losers, four division-series
    losers and four first-round losers, rotated by season."""
    order = CODES[season % 7:] + CODES[:season % 7]
    reached = [5, 4, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1]
    clubs = {c: {"round_reached": 0, "series_won": 0, "bye": False, "in_progress": False} for c in CODES}
    for c, r in zip(order, reached):
        clubs[c]["round_reached"] = r
        clubs[c]["series_won"] = max(r - 1, 0) if r < 5 else 4
    for c in order[4:8]:
        clubs[c]["bye"] = True
        clubs[c]["series_won"] = max(clubs[c]["series_won"] - 1, 0)
    if not complete:
        # the World Series not yet decided: the two pennant winners are alive
        for c in order[:2]:
            clubs[c]["round_reached"] = 4
            clubs[c]["in_progress"] = True
    return {"season": season, "complete": complete, "series": [], "clubs": clubs,
            "source": "fixture", "fetched_at": "2026-10-08T00:00:00+00:00"}


def fixture_inputs() -> dict:
    standings = {c: {} for c in CODES}
    for y in SEASONS:
        for i, c in enumerate(CODES):
            d = int(D[i] / 3) if y == 2020 else D[i]
            gp = 60 if y == 2020 else 162
            w = gp // 2 + d
            standings[c][y] = {"w": w, "l": gp - w, "rd": 6 * d, "gp": gp,
                               "div_champ": (i + y) % 5 == 0,
                               "league_id": 103 if i < 15 else 104}
    post = {y: _bracket(y, complete=(y != 2026)) for y in SEASONS}
    return {
        "standings": standings,
        "flag_disagreements": [[2026, "PHI", True, False]],
        "postseason": post,
        "roster": {c: 20.0 + i for i, c in enumerate(CODES)},
        "outlook": {c: 70.0 + 0.7 * ((i * 7) % 30) for i, c in enumerate(CODES)},
        "farm": {c: 95.0 + 0.4 * ((i * 11) % 30) for i, c in enumerate(CODES)},
        "dvm7": {c: 85 + ((i * 13) % 30) for i, c in enumerate(CODES)},
        "roster_label": ("eWAR v2", "fixture stamp"),
        "roster_as_of": "2026-10-02",
        "payroll": {y: {"rows": {c: (60 + 4 * ((i * 17) % 30)) * 1e6 * (0.37 if y == 2020 else 1.0)
                                 for i, c in enumerate(CODES)}, "fetched": "2026-07-25"}
                    for y in SEASONS},
        "league_min": {y: 700_000 for y in SEASONS},
        "registry": {"models": []},
        "stamps": {},
    }


TODAY = date(2026, 10, 8)


@pytest.fixture()
def inp():
    return fixture_inputs()


@pytest.fixture()
def doc(inp):
    return FX.compute(inp, SEASONS, today=TODAY)


def _strip_time(d):
    d = _copy.deepcopy(d)
    d.pop("generated_at", None)
    return d


# --------------------------------------------------------------------------
# 2.12 items 1 and 2: the scale, the ranks, the letters, the weights
# --------------------------------------------------------------------------

def test_every_identity_holds_on_the_fixture(doc, inp):
    assert FX.identity_failures(doc, inp) == []
    FX.assert_identities(doc, inp)


def test_score_is_100_plus_10z_with_monotone_ranks_and_rank_letters(doc):
    import statistics
    sc = [c["score"] for c in doc["clubs"].values()]
    assert abs(statistics.mean(sc) - 100) <= 0.05 and abs(statistics.pstdev(sc) - 10) <= 0.05
    order = sorted(doc["clubs"].values(), key=lambda c: c["rank"])
    assert [c["rank"] for c in order] == list(range(1, 31))
    assert all(a["score"] >= b["score"] for a, b in zip(order, order[1:]))
    for c in doc["clubs"].values():
        assert c["letter"] == FE.letter_for_rank(c["rank"])


def test_each_live_pillar_is_a_z_across_the_thirty(doc):
    import statistics
    for p in FX.PILLARS:
        zs = [c["pillars"][p]["z"] for c in doc["clubs"].values()]
        assert abs(statistics.mean(zs)) < 0.005 and abs(statistics.pstdev(zs) - 1) < 0.005, p
        for c in doc["clubs"].values():
            assert abs(c["pillars"][p]["score"] - (100 + 10 * c["pillars"][p]["z"])) < 0.06, p


def test_the_constants_are_the_owner_answers_and_equal_the_payload(doc):
    # FS-Q1 results-heavy, FS-Q2 half-life 3, FS-Q3 shown not scored; recorded defaults
    assert FX.FSCORE_LIVE is False
    assert FX.SCHEME == "A"
    assert FX.PILLAR_WEIGHTS == {"results": 0.50, "strength": 0.25, "pipeline": 0.20, "operations": 0.05}
    assert FX.DARK_WEIGHTS == {"results": 0.53, "strength": 0.26, "pipeline": 0.21, "operations": 0.0}
    assert FX.LEG_WEIGHTS == {"strength": {"rd162": 0.50, "roster": 0.30, "outlook": 0.20},
                              "pipeline": {"farm": 0.60, "dvm7": 0.40}}
    assert FX.LADDER == {"kind": "linear", "per_step": 8, "division": 8}
    assert FX.ladder_steps() == [0.0, 8.0, 16.0, 24.0, 32.0, 40.0]
    assert FX.HALF_LIFE == 3.0 and FX.RULE_2020 == "played" and FX.REPLACEMENT_PCT == 0.2944
    assert FX.OPERATIONS_LIVE is True and FX.FSCORE_DUGOUT_LINK is True
    assert FX.MGMT_ADMISSION == {"weight": 0.05, "taken_from": "results"}
    for w in (FX.PILLAR_WEIGHTS, FX.DARK_WEIGHTS, *FX.LEG_WEIGHTS.values()):
        assert abs(sum(w.values()) - 1) < 1e-12
    sch = doc["scheme"]
    assert sch["id"] == FX.SCHEME and sch["pillars"] == FX.PILLAR_WEIGHTS
    assert sch["dark"] == FX.DARK_WEIGHTS and sch["legs"] == FX.LEG_WEIGHTS
    assert sch["ladder"] == {**FX.LADDER, "steps": FX.ladder_steps()}
    assert sch["applied"] == FX.PILLAR_WEIGHTS and sch["operations_live"] is True
    rw = FX.recency_weights(SEASONS)
    assert doc["window"]["weights"] == {str(y): round(rw[y], 4) for y in SEASONS}
    assert doc["window"]["half_life"] == FX.HALF_LIFE and doc["window"]["seasons"] == SEASONS
    assert abs(sum(rw.values()) - 1) < 1e-12 and len(SEASONS) == FX.WINDOW_LEN
    assert round(rw[2026], 3) == 0.257 and round(rw[2020], 3) == 0.064


def test_the_window_is_the_seven_seasons_with_a_complete_regular_season():
    assert FX.window_seasons(date(2026, 10, 8), season_now=2026,
                             regular_season_end="2026-09-27") == SEASONS
    assert FX.window_seasons(date(2026, 9, 27), season_now=2026,
                             regular_season_end="2026-09-27") == list(range(2019, 2026))
    assert FX.window_seasons(date(2026, 10, 8), season_now=2026, regular_season_end=None,
                             live_bracket_on_disk=True) == SEASONS
    assert FX.window_seasons(date(2026, 10, 8), season_now=2026, regular_season_end=None,
                             live_bracket_on_disk=False) == list(range(2019, 2026))


# --------------------------------------------------------------------------
# 2.12 items 3 to 5: standings, brackets, RESULTS
# --------------------------------------------------------------------------

def test_season_values_sum_to_zero_every_season_and_follow_the_formula(doc, inp):
    for y in SEASONS:
        ps = inp["postseason"][y]
        extra = {}
        for c in CODES:
            r = max(ps["clubs"][c]["round_reached"], 0)
            extra[c] = 8 * (1 if inp["standings"][c][y]["div_champ"] else 0) + 8 * r
        mean = sum(extra.values()) / 30
        tot = 0.0
        for c in CODES:
            s = inp["standings"][c][y]
            want = (s["w"] - s["l"]) / 2 + extra[c] - mean
            row = next(r for r in doc["clubs"][c]["seasons"] if r[0] == y)
            assert row[7] == round(want, 1), (c, y)
            tot += want
        assert abs(tot) < 1e-9, y


def test_a_season_whose_records_do_not_balance_is_refused(inp):
    inp["standings"]["LAD"][2023]["w"] += 1
    with pytest.raises(FX.FscoreRefusal, match="sum to"):
        FX.compute(inp, SEASONS, today=TODAY)


def test_division_titles_are_six_a_season_and_the_feed_flag_rows_are_disclosed(doc, inp):
    for y in SEASONS:
        assert len(doc["facts"][str(y)]["division_champions"]) == 6
    assert doc["facts"]["2026"]["flag_disagreements"] == [["PHI", True, False]]
    inp["standings"]["LAD"][2022]["div_champ"] = not inp["standings"]["LAD"][2022]["div_champ"]
    with pytest.raises(FX.FscoreRefusal, match="division champions"):
        FX.compute(inp, SEASONS, today=TODAY)


def test_every_record_equals_the_standings_cache(doc, inp):
    for c in CODES:
        for row in doc["clubs"][c]["seasons"]:
            s = inp["standings"][c][row[0]]
            assert (row[1], row[2], row[3]) == (s["w"], s["l"], s["rd"])
    bad = _copy.deepcopy(doc)
    bad["clubs"]["LAD"]["seasons"][0][1] += 1
    assert any("record" in s for s in FX.identity_failures(bad, inp))


def test_refused_on_a_missing_club(inp):
    inp["standings"]["COL"].pop(2022)
    with pytest.raises(FX.FscoreRefusal, match="missing club"):
        FX.compute(inp, SEASONS, today=TODAY)


def test_refused_on_a_missing_completed_season(inp):
    inp["postseason"][2023] = None
    with pytest.raises(FX.FscoreRefusal, match="no bracket"):
        FX.compute(inp, SEASONS, today=TODAY)
    inp2 = fixture_inputs()
    inp2["postseason"][2024]["complete"] = False
    with pytest.raises(FX.FscoreRefusal, match="not complete"):
        FX.compute(inp2, SEASONS, today=TODAY)


def test_refused_on_a_broken_bracket(inp):
    inp["postseason"][2021]["clubs"]["COL"]["round_reached"] = 5   # two champions
    with pytest.raises(FX.FscoreRefusal, match="broken bracket"):
        FX.compute(inp, SEASONS, today=TODAY)


def test_load_inputs_turns_a_postseason_identity_break_into_a_refusal(monkeypatch):
    import postseason

    def broken(season, **_k):
        raise postseason.PostseasonIdentityError(f"{season}: 2 champions, expected 1")
    monkeypatch.setattr(postseason, "load", broken)
    with pytest.raises(FX.FscoreRefusal, match="bracket breaks"):
        FX.load_inputs(SEASONS)


def test_the_live_postseason_is_in_progress_and_unplayed_steps_count_nothing(doc, inp):
    assert doc["window"]["in_progress"] == [2026]
    assert doc["facts"]["2026"]["complete"] is False and doc["facts"]["2026"]["champion"] is None
    alive = [c for c in CODES if inp["postseason"][2026]["clubs"][c]["in_progress"]]
    assert len(alive) == 2
    for c in CODES:
        row = next(r for r in doc["clubs"][c]["seasons"] if r[0] == 2026)
        assert row[10] is (c in alive)
        assert row[5] <= 4                                   # no title counted yet
        if c in alive:
            assert row[11] == "in the World Series"
            assert doc["clubs"][c]["in_progress"] is True
    for y in SEASONS[:-1]:
        assert all(not r[10] for c in CODES for r in doc["clubs"][c]["seasons"] if r[0] == y)
    assert "fscore_in_progress" in doc["copy"] and doc["copy"]["fscore_in_progress"].startswith("2026 ")


def test_post_text_names_the_round_in_words():
    assert FX.post_text(0, False, False, {}, "NL") == "missed"
    assert FX.post_text(5, True, False, {}, "NL") == "bye, won the World Series"
    assert FX.post_text(3, False, False, {}, "NL") == "lost the NLCS"
    assert FX.post_text(2, True, False, {}, "AL") == "bye, lost the division series"
    assert FX.post_text(1, False, False, {1: 1}, "AL") == "lost the wild card game"
    assert FX.post_text(1, False, True, {1: 3}, "AL") == "in the wild card series"


# --------------------------------------------------------------------------
# the 2020 rule
# --------------------------------------------------------------------------

def test_2020_counts_as_played(doc, inp):
    rw = FX.recency_weights(SEASONS)
    c = "LAD"
    s = inp["standings"][c][2020]
    row = next(r for r in doc["clubs"][c]["seasons"] if r[0] == 2020)
    assert s["gp"] == 60 and row[1] + row[2] == 60          # 60 games, not scaled to 162
    # run differential as played for 2020, per 162 games otherwise
    want = sum(rw[y] * (inp["standings"][c][y]["rd"] if y == 2020 else
                        inp["standings"][c][y]["rd"] * 162 / inp["standings"][c][y]["gp"]) for y in SEASONS)
    assert doc["clubs"][c]["legs"]["rd162"] == round(want, 1)
    # OPERATIONS weights 2020 at 60/162 of its recency weight
    raw = {y: rw[y] * (60 / 162 if y == 2020 else 1) for y in SEASONS}
    tot = sum(raw.values())
    assert doc["window"]["operations_weights"] == {str(y): round(raw[y] / tot, 4) for y in SEASONS}
    assert doc["window"]["rule_2020"] == "played"


# --------------------------------------------------------------------------
# 2.12 items 6 to 8: STRENGTH, PIPELINE, OPERATIONS
# --------------------------------------------------------------------------

def test_roster_and_outlook_z_equal_the_franchise_branch_scores(doc, inp):
    s_roster = FE._score_100(inp["roster"])
    s_outlook = FE._score_100(inp["outlook"])
    s_farm = FE._score_100(inp["farm"])
    for c in CODES:
        legs = doc["clubs"][c]["legs"]
        assert abs(legs["roster_z"] - (s_roster[c] - 100) / 10) <= 0.01, c
        assert abs(legs["outlook_z"] - (s_outlook[c] - 100) / 10) <= 0.01, c
        assert abs(legs["farm_z"] - (s_farm[c] - 100) / 10) <= 0.01, c
        assert legs["dvm7"] == inp["dvm7"][c]


def test_the_roster_label_is_read_from_a_served_stamp_never_typed(doc):
    assert doc["copy"]["roster_leg"] == "team eWAR v2 on the current roster, 2026-10-02"
    lab, where = FX.roster_label({}, {"hitter_leaderboards.json": {"multiyear_war_rate": {"war_provider": "fwar"}}})
    assert lab == "fWAR" and "hitter_leaderboards.json" in where
    assert FX.roster_label({"war_provider": "ewar_v2"}, {})[0] == "eWAR v2"
    with pytest.raises(FX.FscoreRefusal, match="no served WAR provider"):
        FX.roster_label({}, {})
    src = (ROOT / "fscore_export.py").read_text(encoding="utf-8")
    assert '"team eWAR' not in src and "'team eWAR" not in src


def test_a_pillar_short_of_thirty_clubs_is_refused(inp):
    inp["dvm7"].pop("MIA")
    with pytest.raises(FX.FscoreRefusal, match="29 of 30"):
        FX.compute(inp, SEASONS, today=TODAY)


def test_operations_is_the_rank_normal_score_of_wins_above_replacement_per_dollar(doc, inp):
    y = 2024
    floor = 26 * inp["league_min"][y]
    eff = {}
    for c in CODES:
        s = inp["standings"][c][y]
        eff[c] = (s["w"] - 0.2944 * s["gp"]) / (max(inp["payroll"][y]["rows"][c] - floor, 1e6) / 1e6)
    order = sorted(CODES, key=lambda c: (eff[c], c))
    import statistics
    nd = statistics.NormalDist()
    for i, c in enumerate(order):
        row = next(r for r in doc["clubs"][c]["seasons"] if r[0] == y)
        assert row[9] == round(nd.inv_cdf((i + 1) / 31), 2), c


def test_operations_dark_applies_the_declared_vector_and_prints_it(inp, monkeypatch):
    inp["payroll"][2021]["rows"].pop("SEA")
    d = FX.compute(inp, SEASONS, today=TODAY)
    assert d["scheme"]["operations_live"] is False
    assert d["scheme"]["applied"] == FX.DARK_WEIGHTS
    assert "2021" in d["scheme"]["operations_dark_reason"]
    assert d["copy"]["weights_foot"] == "RESULTS 53%, STRENGTH 26%, PIPELINE 21%, OPERATIONS dark"
    assert "OPERATIONS is dark" in d["copy"]["operations_note"]
    assert all(c["pillars"]["operations"] == {"z": None, "score": None} for c in d["clubs"].values())
    assert all(r[9] is None for c in d["clubs"].values() for r in c["seasons"])
    assert FX.identity_failures(d, inp) == []
    # the raw index is the declared dark vector over the three pillars, never pro rata
    c = d["clubs"]["LAD"]
    want = sum(FX.DARK_WEIGHTS[p] * c["pillars"][p]["z"] for p in ("results", "strength", "pipeline"))
    assert abs(c["raw"] - want) < 0.002
    monkeypatch.setattr(FX, "OPERATIONS_LIVE", False)
    d2 = FX.compute(fixture_inputs(), SEASONS, today=TODAY)
    assert d2["scheme"]["operations_live"] is False and d2["scheme"]["applied"] == FX.DARK_WEIGHTS


# --------------------------------------------------------------------------
# 2.12 item 9: hygiene
# --------------------------------------------------------------------------

def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_no_key_or_cell_grouped_by_a_grade_and_no_management_value(doc):
    for k in _keys(doc):
        kl = k.lower()
        assert not re.search(r"(^|_)(e?fv|consensus|grades?)(_|$)", kl), k
        assert "mwpa" not in kl, k
        assert kl not in {"revenue", "revenues", "valuation", "valuations", "decision_quality",
                          "manager_skill"}, k
    assert doc["accountability"]["management"]["scored"] is False
    src = (ROOT / "fscore_export.py").read_text(encoding="utf-8")
    assert "management_board" not in src.split('"""', 2)[2], "management enters no code path"
    bad = _copy.deepcopy(doc)
    bad["clubs"]["LAD"]["efv_cell"] = 1
    bad["clubs"]["LAD"]["mwpa_total"] = 1
    bad["clubs"]["LAD"]["decision_quality"] = 1
    fails = " ".join(FX.identity_failures(bad))
    assert "grade-grouped" in fails and "management value" in fails and "forbidden key" in fails


def test_no_banned_dash_and_no_forecast_word(doc):
    txt = json.dumps(doc, ensure_ascii=False)
    assert chr(0x2014) not in txt and chr(0x2013) not in txt
    src = (ROOT / "fscore_export.py").read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2013) not in src
    blob = " ".join(FX._strings([doc["copy"], doc["what_fscore_does_not_claim"]]))
    for w in ("will", "predicts", "due", "on pace", "expected to", "luck", "regress",
              "trending", "sleeper", "clutch"):
        assert not re.search(r"\b" + re.escape(w) + r"\b", blob, re.I), w
    bad = _copy.deepcopy(doc)
    bad["copy"]["x"] = "this club will win"
    assert any("forecast word" in s for s in FX.identity_failures(bad))


def test_no_fit_or_correlation_between_fscore_and_wins(doc):
    keys = json.dumps(doc).lower()
    for k in ('"corr', '"slope', '"r2"', '"pearson', '"spearman', '"fit"', '"rho"', '"trend'):
        assert k not in keys, k


def test_the_honesty_sentence_and_the_not_claimed_list_ship(doc):
    assert doc["copy"]["fscore_honesty"].startswith("Descriptive:")
    assert "published choice, not an estimate" in doc["copy"]["fscore_honesty"]
    assert any("forecast of wins" in s for s in doc["what_fscore_does_not_claim"])
    assert any("decision-quality grade" in s for s in doc["what_fscore_does_not_claim"])
    assert "no scale was fitted" in FX.__doc__ or "No scale was fitted" in FX.__doc__


def test_the_dugout_switch_drops_the_sentence_and_nothing_else(inp, monkeypatch):
    on = FX.compute(inp, SEASONS, today=TODAY)
    assert on["copy"]["fscore_dugout"] == FX.DUGOUT_SENTENCE
    assert "the running game" in FX.DUGOUT_SENTENCE and "per-agent decision value" in FX.DUGOUT_SENTENCE
    monkeypatch.setattr(FX, "FSCORE_DUGOUT_LINK", False)
    off = FX.compute(fixture_inputs(), SEASONS, today=TODAY)
    assert "fscore_dugout" not in off["copy"]
    a, b = _strip_time(on), _strip_time(off)
    a["copy"].pop("fscore_dugout")
    assert a == b


def test_the_management_admission_rule_is_written_before_any_number():
    doc = FX.__doc__
    assert "THE ADMISSION RULE" in doc and "frozen split-half gate" in doc
    assert "0.05 of" in doc and "taken from RESULTS" in doc


# --------------------------------------------------------------------------
# writing: dark by default, refusal exits 2 and writes nothing
# --------------------------------------------------------------------------

def test_dark_by_default_the_preview_is_off_the_webroot(monkeypatch, tmp_path):
    assert FX.out_path() == FX.PREVIEW_OUT
    assert ".cache" in FX.PREVIEW_OUT.parts and "preview" in FX.PREVIEW_OUT.parts
    monkeypatch.setattr(FX, "FSCORE_LIVE", True)
    assert FX.out_path() == FX.LIVE_OUT == ROOT / "data" / "fscore.json"


def test_main_writes_the_preview_and_never_data(monkeypatch, tmp_path, inp):
    d = FX.compute(inp, SEASONS, today=TODAY)
    monkeypatch.setattr(FX, "PREVIEW_OUT", tmp_path / "preview" / "fscore.json")
    monkeypatch.setattr(FX, "LIVE_OUT", tmp_path / "data" / "fscore.json")
    monkeypatch.setattr(FX, "build", lambda today=None: d)
    assert FX.main([]) == 0
    assert (tmp_path / "preview" / "fscore.json").exists()
    assert not (tmp_path / "data" / "fscore.json").exists()
    assert json.loads((tmp_path / "preview" / "fscore.json").read_text(encoding="utf-8"))["clubs"]["LAD"]["score"] \
        == d["clubs"]["LAD"]["score"]


def test_a_refusal_exits_2_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(FX, "PREVIEW_OUT", tmp_path / "preview" / "fscore.json")
    monkeypatch.setattr(FX, "LIVE_OUT", tmp_path / "data" / "fscore.json")

    def refuse(today=None):
        raise FX.FscoreRefusal("standings 2023: missing club(s) ['COL']")
    monkeypatch.setattr(FX, "build", refuse)
    assert FX.main([]) == 2
    assert not any(tmp_path.rglob("*.json"))


# --------------------------------------------------------------------------
# the nightly order (orchestrator ruling X13)
# --------------------------------------------------------------------------

def _src():
    return (ROOT / "run_monthly.py").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"def {name}(")
    return src[i:src.index(NL + "def ", i + 10)]


def test_the_teams_payload_is_written_after_fscore_every_night():
    src = _src()
    daily = _fn(src, "run_daily")
    i_led = daily.index('_step("d10e. Club Ledger board (ledger_board.json)"')
    i_fx = daily.index('_step("6b7g. F-SCORE board (fscore.json)"')
    i_ts = daily.index('_step("6b7h. Team Stats payload (mlb_team_stats.json)"')
    i_fr = daily.index('_step("6b7d. Franchise board (franchise_board.json)"')
    assert i_led < i_fx < i_ts < i_fr
    # in run_daily's source the team_stats_export call follows the fscore_export call
    assert daily.index("_export_fscore(log)") < daily.index("_export_team_stats(log)")
    body = daily[i_ts:i_fr]
    assert "if chained" not in body, "the Teams payload step is never skipped as chained"
    assert "_export_team_stats(log)" in body
    # the Team Stats payload is written nowhere else
    assert src.count("team_stats_export.export") == 0
    assert "_tse.export(" in _fn(src, "_export_team_stats")
    helper = _fn(src, "_league_teams_payloads")
    assert "team_stats_export" not in helper.split('"""', 2)[2]
    call = "            _export_team_stats(log)" + NL
    assert src.count(call) == 1 and src.count("            _export_fscore(log)" + NL) == 1
    # the labels by commit order: 6b7f is the Awards board, 6b7g and 6b7h are these
    assert src.count('_step("6b7f. Awards board (awards.json)"') == 1
    assert src.count('_step("6b7g.') == 1 and src.count('_step("6b7h.') == 1


def test_the_fscore_step_uses_the_franchise_refusal_idiom_and_is_watched():
    import run_monthly
    body = _fn(_src(), "_export_fscore")
    assert 'type(e).__name__ == "FscoreRefusal"' in body
    assert '_record_ingest("fscore_export", True' in body and '_record_ingest("fscore_export", False' in body
    assert "_fx.build()" in body and "_fx.write(_fxd)" in body
    sx = run_monthly.SCHEDULED_EXPORTS
    assert sx.index("fscore_export") == sx.index("postseason_cache") + 1


# --------------------------------------------------------------------------
# the real data, where its caches are on disk (identity 8 and the full build)
# --------------------------------------------------------------------------

def _real_inputs_or_skip():
    seasons = FX.window_seasons()
    import postseason
    for y in seasons:
        if postseason.load(y) is None:
            pytest.skip(f"postseason {y} not on disk")
    for n in ("war_leaderboards.json", "mlb_projections.json", "timeseries.json"):
        if not (ROOT / "data" / n).exists():
            pytest.skip(f"{n} absent")
    return seasons, FX.load_inputs(seasons)


def test_the_real_payroll_rows_are_the_cached_pages_totals():
    seasons, inp = _real_inputs_or_skip()
    import fa_sources
    hist = fa_sources.read_cached_payroll_history(seasons)
    for y in seasons:
        rows = {FE._canon(r["team"]): float(r["total_payroll_usd"])
                for r in hist["seasons"][y]["payroll"] if r.get("total_payroll_usd") is not None}
        if len(rows) < 30:
            pytest.skip(f"payroll page {y} resolves {len(rows)} clubs")
        assert inp["payroll"][y]["rows"] == rows, y


def test_the_real_build_holds_every_identity():
    seasons, inp = _real_inputs_or_skip()
    d = FX.compute(inp, seasons, today=date.today())
    assert FX.identity_failures(d, inp) == []
    assert len(d["clubs"]) == 30 and d["window"]["seasons"] == seasons
