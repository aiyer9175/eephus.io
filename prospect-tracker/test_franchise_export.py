# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /franchise/ payload (Franchise, D3, 2026-09-23).

THE POINT OF THIS PAGE IS THAT IT COMPUTES ALMOST NOTHING. It re-serves what
every module already publishes, on the scale each was computed on, and derives
exactly two descriptive indexes. The mistakes these tests exist for:

  1. A BRANCH SCORE THAT IS NOT 100 + 10z across the 30 (the farm composite
     measures sd 6.36 and must be re-standardised, not passed through).
  2. A FRANCHISE INDEX BANDED ON THE RAW WEIGHTED MEAN (its sd is below 10; it
     is re-standardised before any rank, letter or tier).
  3. A LETTER THAT DISAGREES WITH ITS RANK, or the storage em-dash sentinel
     leaking into copy.
  4. A DESCRIPTIVE BRANCH THAT GREW A LETTER, A WEIGHT OR A SCORE (nine of the
     twelve carry none); OUTLOOK graded WITHOUT its provisional chip.
  5. A /mlbstats/ LINK CARRYING A SITE CODE (the leaderboards compare the hash
     raw against the StatsAPI code and render an empty board).
  6. COMBINING ou_mkt AND ou_war; SUMMING QUANTILES into a surplus; a 2027
     dollar without the CBA carry-forward flag; a verdict chip lent to
     futures.json (no registry row); a plus metric or letter in DUGOUT.
  7. A DARK SECTION THAT LOOKS LIKE A BUG (every one names its blocker).

The payload is read once per module; build() is exercised only through the
refusal path under tmp_path and never writes a repo file.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "franchise_board.json"
JS = ROOT / "assets" / "franchise.js"
SITE_CODES = {"KCR": "KC", "CHW": "CWS", "WSN": "WSH", "ATH": "ATH", "SFG": "SF",
              "SDP": "SD", "TBR": "TB", "ARI": "AZ"}
GRADED = ("roster", "outlook", "farm")
DESCRIPTIVE = ("season", "fin", "market", "front_office", "dugout", "arbitration",
               "park", "history", "odds")
EM, EN = chr(0x2014), chr(0x2013)


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python franchise_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def clubs(d):
    return {c["code"]: c for c in d["clubs"]}


def _load(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"{name} absent")
    return json.loads(p.read_text(encoding="utf-8"))


def _branch(c, key):
    return next(b for b in c["tree"]["branches"] if b["key"] == key)


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, k, v
            yield from _walk(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


# --------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------

def test_thirty_clubs_and_only_canonical_codes(d, clubs):
    assert len(d["clubs"]) == 30 and len(d["board"]) == 30 and len(d["codes"]) == 30
    assert set(SITE_CODES) <= set(clubs)
    for bad in ("OAK", "Cuba", "AVERAGES", "KC", "CWS", "WSH", "AZ", "SD", "SF", "TB"):
        assert bad not in clubs, bad
    oj = d["accountability"]["org_join"]
    assert oj["war_leaderboards"][1] == 30 and oj["team_outlook"][1] == 30 and oj["org_summary"][1] == 30
    assert oj["fa_meta"][0] > 30 and not set(oj["trade_values_dropped"]) & set(clubs)
    assert oj["trade_values"][0] - oj["trade_values"][1] == len(oj["trade_values_dropped"])
    # mgmt_export keys its style rows on the canonical org since M10-03, so no OAK
    # row reaches this join (it counted 31 raw codes while OAK and ATH were split).
    assert oj["management_teams"][0] == 30 and oj["management_teams"][1] == 30, "one code per org"
    assert oj["standings_ids"] == 30


def test_every_club_carries_a_statsapi_code_and_every_mlbstats_link_uses_it(d, clubs):
    from trades import statsapi_code
    for code, c in clubs.items():
        sapi = c["statsapi_code"]
        assert sapi == statsapi_code(code), code
        assert sapi == SITE_CODES.get(code, code), code
        for k, href in c["links"].items():
            if k.startswith("mlbstats_"):
                assert href.endswith("&team=" + sapi), (code, k, href)
                assert "&team=" + code not in href or sapi == code, (code, k, href)


def test_logo_slug_matches_build_site_espn_slugs(clubs):
    import build_site
    for code, c in clubs.items():
        assert c["logo"].endswith(f"/{build_site.ESPN_SLUGS[code]}.png"), (code, c["logo"])


# --------------------------------------------------------------------------
# Mistakes 1 and 2: the two derived indexes
# --------------------------------------------------------------------------

def test_every_graded_branch_has_thirty_scores_mean_100_sd_10(clubs):
    for key in GRADED:
        xs = [_branch(c, key)["score"] for c in clubs.values()]
        assert len(xs) == 30 and all(x is not None for x in xs), key
        assert abs(statistics.mean(xs) - 100) < 0.1, (key, statistics.mean(xs))
        assert abs(statistics.pstdev(xs) - 10) < 0.1, (key, statistics.pstdev(xs))


def test_branch_score_is_100_plus_10z_of_the_served_value(clubs):
    from franchise_export import _score_100
    # the formula, pinned on the served roster values
    vals = {code: _branch(c, "roster")["value"] for code, c in clubs.items()}
    got = _score_100(vals)
    mu, sd = statistics.mean(vals.values()), statistics.pstdev(vals.values())
    for code, v in vals.items():
        assert got[code] == round(100 + 10 * (v - mu) / sd, 1), code
        assert _branch(clubs[code], "roster")["score"] == got[code], code
    # None stays None, a degenerate pool scores 100
    assert _score_100({"a": 1.0, "b": None, "c": 3.0})["b"] is None
    assert _score_100({"a": 2.0, "b": 2.0}) == {"a": 100.0, "b": 100.0}
    # PARITY WITH THE STORAGE PRECEDENT: storage._zscore_to_100 is a closure and
    # cannot be imported, so the formula is checked against the served
    # org_summary score_100 leaves on a leaf every org carries.
    ts = _load("timeseries.json")
    leaf = {}
    for o in ts.get("org_summary") or []:
        lf = (o.get("tree") or {}).get("fin_war_per_m") or {}
        if lf.get("value") is not None and lf.get("score_100") is not None and not lf.get("sparse"):
            leaf[o["org"]] = (lf["value"], lf["score_100"])
    if len(leaf) == 30:
        ours = _score_100({k: v[0] for k, v in leaf.items()})
        for k, (v, served) in leaf.items():
            assert abs(ours[k] - served) <= 0.15, (k, ours[k], served)


def test_index_is_mean_100_sd_10_after_re_standardising(d, clubs):
    W = d["weights"]
    raw, scores = [], []
    for c in clubs.values():
        ix = c["index"]
        wm = sum(W[k] * _branch(c, k)["score"] for k in GRADED)
        assert abs(ix["raw_weighted_mean"] - wm) < 0.01, c["code"]
        raw.append(ix["raw_weighted_mean"])
        scores.append(ix["score"])
    assert statistics.pstdev(raw) < 9.9, "the raw weighted mean of z-scores has sd below 10 and is never tiered raw"
    assert abs(statistics.mean(scores) - 100) < 0.1 and abs(statistics.pstdev(scores) - 10) < 0.1
    assert d["league"]["pools"]["raw_weighted_mean"]["sd"] < 10


def test_weights_sum_to_one_over_graded_branches_only(d, clubs):
    assert abs(sum(d["weights"].values()) - 1.0) < 1e-9
    assert set(d["weights"]) == set(GRADED)
    assert d["weights"] == {"roster": 0.40, "outlook": 0.30, "farm": 0.30}
    for c in clubs.values():
        for b in c["tree"]["branches"]:
            if b["kind"] == "graded":
                assert b["weight"] == d["weights"][b["key"]]
            else:
                assert not b["weight"]


def test_index_rank_is_monotone_in_index_score(clubs):
    rows = sorted(clubs.values(), key=lambda c: c["index"]["rank"])
    assert [c["index"]["rank"] for c in rows] == list(range(1, 31))
    for a, b in zip(rows, rows[1:]):
        assert a["index"]["score"] >= b["index"]["score"]


# --------------------------------------------------------------------------
# Mistake 3: letters and the sentinel
# --------------------------------------------------------------------------

def test_letter_matches_rank_by_storage_letter_grade(clubs):
    import storage
    for c in clubs.values():
        assert c["index"]["letter"] == storage._letter_grade(c["index"]["rank"], 30)
        for key in ("roster", "outlook"):
            b = _branch(c, key)
            assert b["letter"] == storage._letter_grade(b["rank"], 30), (c["code"], key)
    letters = sorted({c["index"]["letter"] for c in clubs.values()})
    assert "A+" in letters and "F" in letters


def test_no_em_dash_sentinel_survives(d):
    txt = ART.read_text(encoding="utf-8")
    assert EM not in txt and EN not in txt
    from franchise_export import letter_for_rank
    assert letter_for_rank(None) is None
    for _p, _k, v in _walk(d):
        if isinstance(v, str):
            assert EM not in v and EN not in v


# --------------------------------------------------------------------------
# Mistake 4: descriptive branches, and OUTLOOK's chip
# --------------------------------------------------------------------------

def test_descriptive_branches_carry_no_letter_no_weight_no_score(d, clubs):
    assert d["descriptive"] == list(DESCRIPTIVE) and d["graded"] == list(GRADED)
    for c in clubs.values():
        keys = [b["key"] for b in c["tree"]["branches"]]
        assert keys == list(GRADED) + list(DESCRIPTIVE), c["code"]
        for b in c["tree"]["branches"]:
            if b["kind"] == "descriptive":
                assert b["letter"] is None and b["score"] is None and b["rank"] is None and not b["weight"], (c["code"], b["key"])
        # SEASON is descriptive under the OUTLOOK decision (D6 alternative)
        assert _branch(c, "season")["kind"] == "descriptive"


def test_outlook_is_graded_provisional_with_the_chip_and_wins_parity(d, clubs):
    proj = _load("mlb_projections.json")
    from trades import canonical_org
    wins = {canonical_org(r["team"]): r["wins"] for r in proj["team_outlook"]}
    for code, c in clubs.items():
        b = _branch(c, "outlook")
        assert b["kind"] == "graded" and b["provisional"] is True and b["letter"] is not None
        assert b["verdict"] == "provisional" and b["verdict_model"] == "team_win_projections"
        assert b["value"] == wins[code] == c["sections"]["outlook"]["wins"], code
        assert c["sections"]["outlook"]["provisional"] is True
    assert "provisional" in d["copy"]["root_sentence"].lower()
    assert "thirty percent" in d["copy"]["root_sentence"].lower()
    assert d["copy"]["outlook_chip"] == "provisional"


def test_season_is_descriptive_and_wins_equal_the_standings_by_team_id(clubs):
    from trades import canonical_org_from_id
    raw = json.loads((ROOT / ".cache" / "statsapi_standings_2026.json").read_text(encoding="utf-8"))
    by = {}
    for rec in raw["records"]:
        for tr in rec["teamRecords"]:
            by[canonical_org_from_id(tr["team"]["id"])] = (tr["wins"], tr["losses"], tr["runDifferential"], int(tr["divisionRank"]))
    assert len(by) == 30
    for code, c in clubs.items():
        s = c["sections"]["season"]
        assert (s["wins"], s["losses"], s["run_diff"], s["division_rank"]) == by[code], code
        assert _branch(c, "season")["headline"] == f"{s['wins']}-{s['losses']}"


# --------------------------------------------------------------------------
# The division champion (FS_1, 2026-10-01): one rule, never the feed's flag
# --------------------------------------------------------------------------

def _tr(tid, name, rank, clinch, feed_flag, w, l):
    return {"team": {"id": tid, "name": name}, "divisionRank": rank, "clinchIndicator": clinch,
            "divisionChamp": feed_flag, "clinched": clinch is not None, "wins": w, "losses": l}


# Trimmed from .cache/statsapi_standings_2026.json (NL East, division 204):
# the feed flags the second-place Phillies (rank 2, 'w') beside the Braves.
NL_EAST_2026 = [{"division": {"id": 204}, "teamRecords": [
    _tr(144, "Braves", "1", "y", True, 94, 68),
    _tr(143, "Phillies", "2", "w", True, 88, 74),
    _tr(146, "Marlins", "3", None, False, 80, 82),
]}]
# Trimmed from .cache/statsapi_standings_2012.json (NL West, division 203):
# the feed leaves divisionChamp off the first-place Giants.
NL_WEST_2012 = [{"division": {"id": 203}, "teamRecords": [
    _tr(137, "Giants", "1", "y", False, 94, 68),
    _tr(119, "Dodgers", "2", None, False, 86, 76),
]}]


def test_phi_2026_is_not_a_division_champion_and_atl_is():
    import franchise_export as fe
    assert fe.division_champions(NL_EAST_2026, live=True) == {204: "ATL"}
    assert fe.division_champions(NL_EAST_2026, live=False) == {204: "ATL"}


def test_sfg_2012_is_a_champion_although_the_feed_omits_the_flag():
    import franchise_export as fe
    assert fe.division_champions(NL_WEST_2012, live=False) == {203: "SFG"}


def test_a_live_division_leader_without_y_or_z_is_not_yet_a_champion():
    import franchise_export as fe
    live = [{"division": {"id": 204}, "teamRecords": [
        _tr(144, "Braves", "1", None, False, 60, 40),
        _tr(143, "Phillies", "2", None, False, 58, 42),
    ]}]
    assert fe.division_champions(live, live=True) == {204: None}
    assert fe.division_champions(live, live=False) == {204: "ATL"}
    clinched_best = [{"division": {"id": 204}, "teamRecords": [_tr(144, "Braves", "1", "z", False, 100, 62)]}]
    assert fe.division_champions(clinched_best, live=True) == {204: "ATL"}


def test_a_division_without_one_rank_one_club_maps_to_none_not_a_refusal():
    import franchise_export as fe
    tied = [{"division": {"id": 204}, "teamRecords": [
        _tr(144, "Braves", "1", None, False, 81, 81),
        _tr(143, "Phillies", "1", None, False, 81, 81),
    ]}]
    assert fe.division_champions(tied, live=False) == {204: None}


def test_a_feed_flag_on_a_second_place_club_yields_exactly_one_disagreement_row(tmp_path, monkeypatch):
    import franchise_export as fe
    (tmp_path / f"statsapi_standings_{fe.SEASON_NOW}.json").write_text(
        json.dumps({"records": NL_EAST_2026}), encoding="utf-8")
    monkeypatch.setattr(fe, "CACHE", tmp_path)
    monkeypatch.setattr(fe, "STANDINGS_FIRST", fe.SEASON_NOW)
    rows, _ids, disagreements = fe._standings()
    assert disagreements == [[fe.SEASON_NOW, "PHI", True, False]]
    assert rows["ATL"][fe.SEASON_NOW]["div_champ"] is True
    assert rows["PHI"][fe.SEASON_NOW]["div_champ"] is False
    assert rows["PHI"][fe.SEASON_NOW]["clinched"] is True
    assert set(rows["PHI"][fe.SEASON_NOW]) == {"w", "l", "rs", "ra", "rd", "rank", "gp", "pct",
                                               "clinched", "div_champ", "division_id"}


def test_served_champions_are_one_rank_one_club_per_division_and_the_rows_disclose_the_feed(d, clubs):
    champs = [c["code"] for c in clubs.values() if c["sections"]["season"]["division_champ"]]
    assert all(clubs[c]["sections"]["season"]["division_rank"] == 1 for c in champs), champs
    assert len({clubs[c]["division"] for c in champs}) == len(champs) <= 6
    assert clubs["PHI"]["sections"]["season"]["division_champ"] is False
    rows = d["accountability"]["standings_flag_disagreements"]
    for season, code, feed_flag, derived in rows:
        assert isinstance(season, int) and code in clubs and feed_flag is not derived
    assert [r for r in rows if r[0] == d["season_now"]] == [[d["season_now"], "PHI", True, False]]


def test_the_division_fix_leaves_every_other_payload_key_unchanged(d, clubs):
    assert set(d["accountability"]) == {"registry_verdicts", "registry_checked_at", "n_clubs", "org_join",
                                        "bwar_census", "standings_flag_disagreements",
                                        "score_formula", "index_formula"}
    for code, c in clubs.items():
        assert list(c["sections"]["season"]) == [
            "wins", "losses", "games", "pct", "run_diff", "rs", "ra", "division_rank", "clinched",
            "division_champ", "cur_wins_outlook", "cur_pct_outlook", "pythag_pct", "actual_pct",
            "talent_prior_pct", "blend_weights", "gb", "rem_games", "basis"], code


def test_roster_ewar_equals_war_leaderboard_teams(clubs):
    from trades import canonical_org
    war = _load("war_leaderboards.json")
    by = {canonical_org(r["team"]): r["war"] for r in war["teams"]}
    assert len(by) == 30 and any(t["team"] in ("KC", "CWS", "WSH") for t in war["teams"]), "the board carries StatsAPI codes"
    for code, c in clubs.items():
        assert _branch(c, "roster")["value"] == by[code] == c["sections"]["roster"]["war"], code


def test_farm_letter_and_rank_pass_through_and_score_is_re_standardised(clubs):
    from franchise_export import _score_100
    from trades import canonical_org
    ts = _load("timeseries.json")
    os_ = {canonical_org(o["org"]): o for o in ts["org_summary"]}
    fs = {code: os_[code]["farm_score"] for code in clubs}
    std = _score_100(fs)
    assert statistics.pstdev(fs.values()) < 8, "farm_score is NOT 100 + 10z (measured sd about 6.4); it must be re-standardised"
    for code, c in clubs.items():
        b = _branch(c, "farm")
        assert b["letter"] == os_[code]["grades"]["overall"], code
        assert b["rank"] == os_[code]["farm_rank"], code
        assert b["score"] == std[code] and c["sections"]["farm"]["score"] == std[code], code
        assert c["sections"]["farm"]["farm_score"] == fs[code]


# --------------------------------------------------------------------------
# Mistakes 5 and 6: the sections
# --------------------------------------------------------------------------

def test_fin_is_descriptive_and_space_equals_fa_meta_space_labelled_spotrac_247m_basis(d, clubs):
    fm = _load("fa_meta.json")
    ledger = (ROOT / "data" / "ledger_board.json")
    lg = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else None
    for code, c in clubs.items():
        f = c["sections"]["fin"]
        assert f["descriptive"] is True and _branch(c, "fin")["kind"] == "descriptive"
        # Spotrac's space unless the club's guaranteed AAV stands in (owner answer M13-1)
        if f["tax_payroll_2027_source"] == "spotrac":
            assert f["space_2027"]["spotrac_usd"] == fm["teams"][code]["space"], code
        if lg:
            assert f["space_2027"] == lg["clubs"][code]["payroll"]["space_2027"], code
            assert f["space_2027"]["spotrac_basis_usd"] == 247_000_000
            assert f["cost_plus"] == lg["clubs"][code]["indexes"]["cost_plus"], code
            assert f["space_2027"]["platform_basis_usd"] != f["space_2027"]["spotrac_basis_usd"], "two bases, never mixed"
    assert "247M basis" in d["copy"]["space_label_spotrac"]
    assert d["sections_status"]["fin"]["descriptive"] is True
    if lg:
        assert d["sections_status"]["fin"]["headline"].startswith("Cost+")


def test_odds_quotes_the_playoff_odds_registry_row_and_the_monte_carlo_sentence(d, clubs):
    fu = _load("futures.json")
    reg = {m["model_id"]: m for m in _load("model_registry.json")["models"]}
    row = reg["playoff_odds_sim"]
    assert row["eval_artifact"] == "data/futures.json"
    assert d["sections_status"]["odds"]["registry_row"] == "playoff_odds_sim"
    assert "odds_no_registry" not in d["copy"]
    assert d["copy"]["odds_interval"] == fu["what_the_intervals_are"]
    # the season-over line is quoted from the Futures payload, never rebuilt here
    assert d["copy"]["odds_as_of"] == (fu.get("as_of_note") or "")
    assert "Monte Carlo" in d["copy"]["odds_interval"]
    for c in clubs.values():
        o = c["sections"]["odds"]
        assert o["registry_row"] == "playoff_odds_sim" and o["verdict"] == row["verdict"]
        assert "no registry row" not in o["basis"]
        b = _branch(c, "odds")
        assert b["verdict"] == row["verdict"] and b["verdict_model"] == "playoff_odds_sim"


# --------------------------------------------------------------------------
# RFR01 (2026-10-02): a settled season's ODDS agree with its SEASON tiles
# --------------------------------------------------------------------------

def test_served_settled_odds_agree_with_the_final_standings_and_the_bracket_seeds(clubs):
    """Over the SERVED artifacts. Once futures.json is built past
    regular_season_end, every club's Division equals its division_champ flag,
    Bye is 1 only for bracket seeds 1 and 2 per league, Playoffs only for a
    seeded club, and Projected wins with both ends of its band equal the final
    wins. A phantom game once served CLE 74.9% Division beside 'division
    champion' and NYY 93.5 projected wins on a 93-68 final."""
    import franchise_export as fe
    from trades import canonical_org
    fu = _load("futures.json")
    if not fe.futures_settled(fu):
        pytest.skip("futures.json is not past regular_season_end")
    bs = _load("bracket_sim.json")
    # bracket_sim lists the 12 postseason clubs only; a club it omits is unseeded
    seeds = {canonical_org(r["team"]): r.get("seed") for r in bs["clubs"]}
    assert set(seeds) <= set(clubs) and len(seeds) == 12
    for lg in ("AL", "NL"):
        got = sorted(r["seed"] for r in bs["clubs"] if r["league"] == lg and r.get("seed"))
        assert got == [1, 2, 3, 4, 5, 6], (lg, got)
    seeds = {code: seeds.get(code) for code in clubs}
    for code, c in clubs.items():
        o, s = c["sections"]["odds"], c["sections"]["season"]
        assert o["division_pct"] == float(s["division_champ"]), (code, o["division_pct"], s["division_champ"])
        assert o["bye_pct"] == (1.0 if seeds[code] in (1, 2) else 0.0), (code, o["bye_pct"], seeds[code])
        assert o["playoff_pct"] == (1.0 if seeds[code] else 0.0), (code, o["playoff_pct"], seeds[code])
        assert o["proj_wins"] == s["wins"] and o["p10"] == o["p90"] == s["wins"], (code, o["proj_wins"], o["p10"], o["p90"], s["wins"])
    assert fe.settled_odds_disagreements(list(clubs.values()), fu, seeds) == []


def _odds_doc(code, wins, champ, odds):
    return {"code": code, "sections": {"season": {"wins": wins, "division_champ": champ}, "odds": odds}}


PHANTOM = [  # the served 2026-10-01 rows, one phantom game in futures.json
    _odds_doc("CLE", 85, True, {"division_pct": 0.749, "bye_pct": 0.749, "playoff_pct": 1.0,
                                "proj_wins": 85, "p10": 85, "p90": 85}),
    _odds_doc("NYY", 93, False, {"division_pct": 0.0, "bye_pct": 0.0, "playoff_pct": 1.0,
                                 "proj_wins": 93.5, "p10": 93, "p90": 94}),
]
PHANTOM_SEEDS = {"CLE": 2, "NYY": 4}


def test_the_settled_odds_guard_names_every_phantom_field_and_only_after_the_end_date():
    import franchise_export as fe
    after = {"season": fe.SEASON_NOW, "generated_at": "2026-10-02T01:28:32+00:00", "regular_season_end": "2026-09-27"}
    bad = fe.settled_odds_disagreements(PHANTOM, after, PHANTOM_SEEDS)
    assert bad == [["CLE", "division_pct", 0.749, 1.0], ["CLE", "bye_pct", 0.749, 1.0],
                   ["NYY", "proj_wins", 93.5, 93], ["NYY", "p90", 94, 93]]
    # without the bracket the seed-based fields are not checked
    assert [r[:2] for r in fe.settled_odds_disagreements(PHANTOM, after, None)] == [
        ["CLE", "division_pct"], ["NYY", "proj_wins"], ["NYY", "p90"]]
    # in season, on the end date itself, another season, or no dates: nothing is settled
    for fu in ({**after, "generated_at": "2026-09-20T04:00:00+00:00"},
               {**after, "generated_at": "2026-09-27T04:00:00+00:00"},
               {**after, "season": fe.SEASON_NOW - 1},
               {**after, "regular_season_end": None}, {}):
        assert fe.futures_settled(fu) is False
        assert fe.settled_odds_disagreements(PHANTOM, fu, PHANTOM_SEEDS) == []


def test_export_refuses_a_settled_season_whose_odds_contradict_the_standings(tmp_path, monkeypatch):
    import franchise_export as fe
    fu = _load("futures.json")
    if not fe.futures_settled(fu):
        pytest.skip("futures.json is not past regular_season_end")
    real = fe._j

    def phantom(name, base=fe.DATA):
        doc = real(name, base)
        if name == "futures.json":
            doc = json.loads(json.dumps(doc))
            for row in doc["clubs"]:
                if row["team"] == "NYY":
                    row["projWins"], row["winTotalP90"] = row["projWins"] + 0.5, row["winTotalP90"] + 1
        return doc
    monkeypatch.setattr(fe, "_j", phantom)
    monkeypatch.setattr(fe, "OUT", tmp_path / "franchise_board.json")
    with pytest.raises(fe.FranchiseRefusal) as exc:
        fe.build()
    assert "odds:" in str(exc.value) and "'NYY', 'proj_wins'" in str(exc.value)
    assert fe.main() == 2
    assert not (tmp_path / "franchise_board.json").exists(), "a refusal never writes"


def test_every_section_verdict_equals_its_registry_row(d, clubs):
    reg = {m["model_id"]: m for m in _load("model_registry.json")["models"]}
    quoted = {r["model_id"] for r in d["accountability"]["registry_verdicts"]}
    n = 0
    for c in clubs.values():
        for b in c["tree"]["branches"]:
            if b["verdict_model"]:
                assert b["verdict_model"] in reg and b["verdict_model"] in quoted, (c["code"], b["key"])
                assert b["verdict"] == reg[b["verdict_model"]]["verdict"], (c["code"], b["key"])
                n += 1
    assert n >= 30 * 8


def test_park_factors_come_from_fa_meta_not_a_slate(clubs):
    fm = _load("fa_meta.json")
    n = 0
    for code, c in clubs.items():
        p = c["sections"]["park"]
        assert p["tiered"] is False
        assert p["factors"] == fm["park_factors"].get(code), code
        if p["factors"]:
            n += 1
        else:
            assert p["short_window"] == fm["park_factors_short_window"]["orgs"][code], code
        for _path, k, _v in _walk(p):
            assert "slate" not in str(k).lower() and "bet" not in str(k).lower()
    assert n == len(fm["park_factors"])


def test_realized_fa_value_is_labelled_not_skill_with_method_and_coverage(d, clubs):
    st = d["sections_status"]["market_realized"]
    assert st["live"] is True and st["method"] == "level_proration_backcast_dpw_v1"
    assert st["coverage_by_winter"] and st["coverage_by_winter"][-1][1] == 0, "the current winter has no elapsed season"
    assert "not skill" in d["copy"]["market_realized_sentence"] and "counterfactual" in d["copy"]["market_realized_sentence"]
    for c in clubs.values():
        r = c["sections"]["market"]["realized"]
        assert r["not_skill"] is True and r["method"] == st["method"]
        assert _branch(c, "market")["letter"] is None
        tot = r["totals"]
        assert tot["n_covered"] <= tot["n"]


def test_fin_surplus_is_the_ledger_mlb_leg_only_with_no_farm_overlap(d, clubs):
    """Owner answer M13-2: the FIN surplus figure is the Club Ledger's MLB leg
    (surNpv over the club's veteran rows) on all 30 clubs, its label says so,
    and the Trade Machine currency, which carries the farm, is gone from FIN."""
    lg = _load("ledger_board.json")
    import franchise_export as F
    assert "MLB leg only" in d["copy"]["mlb_leg_label"] and "no farm" in d["copy"]["mlb_leg_label"]
    assert "never overlaps" in d["copy"]["mlb_leg_note"]
    assert "trade_currency_label" not in d["copy"]
    for code, c in clubs.items():
        f = c["sections"]["fin"]
        assert "roster_surplus_ev" not in f, code
        ml = f["mlb_leg"]
        assert ml["mlb_mm"] == lg["clubs"][code]["surplus"]["mlb_mm"], code
        assert ml["by_salsrc_mm"] == lg["clubs"][code]["surplus"]["mlb_by_salsrc_mm"], code
        assert "never of quantiles" in ml["basis"] and "never overlaps the farm" in ml["basis"], code
        for k in ml:
            assert "p10" not in k and "p90" not in k and "lo" not in k and "hi" not in k
        leaves = {x["key"]: x for x in _branch(c, "fin")["leaves"]}
        assert "roster_surplus_ev" not in leaves, code
        assert leaves["mlb_leg"]["label"] == F.MLB_LEG_LABEL == d["copy"]["mlb_leg_label"], code
        assert leaves["mlb_leg"]["value"] == ml["mlb_mm"], code


def test_fin_cost_plus_carries_the_ledger_parts_and_numerator(d, clubs):
    """M13-4 / COSTPLUS-1: FIN re-serves the Ledger's three denominator parts
    and its numerator less the locked free agents, never their sum."""
    lg = _load("ledger_board.json")
    for code, c in clubs.items():
        f, I = c["sections"]["fin"], lg["clubs"][code]["indexes"]
        assert f["cost_plus_parts"] == I["cost_plus_parts"], code
        assert f["locked_fa_2027"] == I["locked_fa_2027"], code
        assert f["proj_war_2027_ex_fa"] == I["proj_war_2027_ex_fa"] and f["usd_per_win"] == I["usd_per_win"], code
        assert f["tax_payroll_2027"] == lg["clubs"][code]["payroll"]["cbt_basis_2027"]["usd"], code
    for k in ("cost_plus_part_labels", "cost_plus_numerator_label", "cost_plus_parts_note", "cbt_basis_aav_label"):
        assert d["copy"][k] == lg["copy"][k], k


def test_arb_ou_mkt_and_ou_war_are_never_combined(d, clubs):
    ah = _load("arb_history.json")
    assert d["copy"]["never_combine"] == ah["field_key"]["never_combine"]
    for c in clubs.values():
        a = c["sections"]["arbitration"]
        assert "ou_mkt_total_usd" in a and "ou_war_total_usd" in a
        for _path, k, _v in _walk(c):
            ks = str(k).lower()
            assert not ("ou_mkt" in ks and "ou_war" in ks), k
            assert ks not in ("ou_total", "ou_combined", "ou_sum"), k
        assert a["verdict"] == "provisional"
        # owner answer M10-4: tendered wording, never "upper bound"
        assert "assumes every player is tendered" in d["copy"]["arb_tender_note"]
        assert "a non-tender lowers the figure" in d["copy"]["arb_tender_note"]
        assert "arb_upper_bound" not in d["copy"]
        assert "upper bound" not in json.dumps(c, ensure_ascii=False).lower()


def test_every_2027_dollar_carries_the_cba_carry_forward_flag(d, clubs):
    assert "2022 CBA carry-forward" in d["copy"]["cba_banner"]
    for c in clubs.values():
        for blk in ("fin", "market", "arbitration"):
            assert c["sections"][blk]["cba_banner"] is True, (c["code"], blk)


def test_dugout_carries_no_plus_metric_and_no_letter(clubs):
    for c in clubs.values():
        dg = c["sections"]["dugout"]
        assert dg["plus_metric"] is False and dg["letter"] is None
        assert _branch(c, "dugout")["letter"] is None and _branch(c, "dugout")["score"] is None
        for _path, k, _v in _walk(dg):
            ks = str(k).lower()
            assert "plus" not in ks or ks == "plus_metric", k
            assert "skill" not in ks and "grade" not in ks and "letter" != ks or ks == "letter"
        fam = dg["realized"]["families"]
        keys = [f[0] for f in fam]
        assert "defensive_sub" not in keys, "defensive subs carry a count only, never a realized figure"
        for f in fam:
            assert f[0] in ("pitching_change", "pinch_hit", "pinch_run", "intentional_walk", "bunt", "steal")


def test_dugout_copy_contains_realized_value_not_skill_and_the_counterfactual_sentence(d):
    s = d["copy"]["dugout_sentence"]
    assert s.startswith("Realized value, not skill.")
    assert "the runner held, the starter left in, was never observed" in s
    assert "nothing on this page ranks a manager or a club by decision quality" in s
    assert "bounded null" in s
    assert d["copy"]["dugout_realized_tag"] == "realized"


def test_the_dugout_sentence_names_the_families_the_table_shows(d, clubs):
    """M10-07. The sentence said the reliever and the pinch hitter would come "once the
    next families land" while the same table showed both. It is now read off the
    decision ledger's summed families, and every family row is one of them."""
    import franchise_export as FE
    mgmt = _load("management_board.json")
    fams = mgmt["decisions"]["families"]
    s = d["copy"]["dugout_sentence"]
    assert "once the next families land" not in s
    for c in clubs.values():
        for f in c["sections"]["dugout"]["realized"]["families"]:
            assert fams[f[0]]["summed"] is True, f[0]
            assert FE.DUGOUT_HAPPENED[f[0]] in s, f[0]
    assert FE._dugout_sentence(["steal"]).count("the run sent.") == 1
    assert "the reliever called" not in FE._dugout_sentence(["steal", "bunt"])


def test_every_leaf_names_its_basis_and_kind(d, clubs):
    kinds = set(d["field_key"]["tree.branches[].leaves[].kind"].replace(" ", "").split("|"))
    for c in clubs.values():
        for b in c["tree"]["branches"]:
            assert b["basis"] and b["title"] and b["label"], (c["code"], b["key"])
            assert b["leaves"], (c["code"], b["key"])
            for lf in b["leaves"]:
                assert lf["basis"] and lf["kind"] in kinds, (c["code"], b["key"], lf["key"], lf["kind"])
                assert lf["link"], (c["code"], b["key"], lf["key"])
                if lf["kind"] in ("idx", "war"):
                    assert lf["ladder"] in (None, "z", "ratio", "run", "rosterWar"), (b["key"], lf["key"])
                else:
                    assert lf["ladder"] is None, (b["key"], lf["key"])


# --------------------------------------------------------------------------
# Deep links: every key a target module actually reads
# --------------------------------------------------------------------------

def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_every_link_uses_a_key_the_target_module_reads(clubs):
    mlbstats, proj, fa, betting = _src("assets/mlbstats.js"), _src("assets/projections.js"), _src("assets/fa.js"), _src("assets/betting.js")
    prospx, parks, arb, mgmt = _src("prospx/index.html"), _src("assets/parks.js"), _src("assets/arbitration.js"), _src("assets/management.js")
    assert re.search(r"section=\(bullpen\|starters\|hitters\|leverage\|defense\|war\)", mlbstats)
    for key in ("view=(relievers|teams|depth)", "sview=(starters|teams|charts)", "hview=(hitters|teams|charts)",
                "dview=(fielders|teams|charts)", "wview=(players|teams)", "team=\\(\\[A-Z\\]\\{2,3\\}\\)"):
        assert re.search(key.replace("(", "\\(").replace(")", "\\)").replace("|", "\\|") if "team=" not in key else key, mlbstats), key
    assert 'p.get("team")' in proj and '"teams", "accountability"' in proj and 'p.get("player")' in proj
    assert 'p.get("view")' in fa and 'p.get("team")' in fa and 'p.get("winter")' in fa
    assert '"teams"' in betting and '"futures"' in betting
    assert 'p.has("farm-org")' in prospx and 'p.has("ftab")' in prospx and 'p.get("ftree")' in prospx and 'p.has("tab")' in prospx
    assert re.search(r"\^#\(board\|leagues\|method\)", parks)
    assert 'sec === "history" || sec === "teams" || sec === "model"' in arb
    assert "section=(league|running|bunt|decisions|clubs" in mgmt and "team=([A-Z]{2,3})" in mgmt
    narrows = "TEAM_NARROW_RE" in arb
    for code, c in clubs.items():
        L = c["links"]
        assert L["team_outlook"] == "/projections/#view=teams" and L["roster_board"] == f"/projections/#team={code}"
        assert L["farm"] == f"/prospx/#farm-org={code}" and L["tendencies"].endswith("&ftab=tendencies") and L["farm_tree"].endswith("&ftree=simple")
        assert L["fa_fits"] == f"/fa/#view=fits&team={code}" and L["fa_archive"].startswith("/fa/#view=archive&winter=")
        assert L["management_club"] == f"/management/#section=clubs&team={code}"
        assert L["arbitration_teams"] == (f"/arbitration/#teams&team={code}" if narrows else "/arbitration/#teams")
        assert L["parks"] == "/parks/" and L["hof"] == "/hof/"
        assert L["betting_teams"] == "/betting/#section=teams" and L["betting_futures"] == "/betting/#section=futures"
        assert L["ledger"] in (None, f"/ledger/#team={code}")
        for k, href in L.items():
            if href:
                assert EM not in href and " " not in href, (k, href)


def test_dark_sections_name_their_blocker(d, clubs):
    st = d["sections_status"]
    assert st["park_attendance"]["live"] is False and "D11" in st["park_attendance"]["blocked_on"]
    assert st["manager_names"]["live"] is False and st["manager_names"]["blocked_on"]
    for k, v in st.items():
        if v.get("live") is False:
            assert v.get("blocked_on"), k
    for s in d["what_this_page_does_not_claim"]:
        assert isinstance(s, str) and s
    assert any("Hall of Fame" in s and "plaque" in s for s in d["what_this_page_does_not_claim"])
    assert any("pennants" in s for s in d["what_this_page_does_not_claim"])


def test_the_hall_of_fame_tile_re_serves_the_hof_franchise_credit(d, clubs):
    """Owner answer 2026-09-25 (final-pass batch 6): the tile is lit on the frozen
    rule and re-serves /hof/'s Franchises section without recounting it. Every
    club's count and inductee list matches hof_board, and the 30 counts plus the
    defunct bucket add up to every credited inductee."""
    hof = json.loads((ROOT / "data" / "hof_board.json").read_text(encoding="utf-8"))
    fr = hof["sections"]["franchises"]
    st = d["sections_status"]["history_hof"]
    assert fr["live"] is True and st["live"] is True
    assert st["rule"] == fr["rule"] and st["rule_frozen"] == "2026-09-25"
    by_code = {c["code"]: c for c in fr["clubs"]}
    rows = {r["id"]: r for r in fr["inductees"]}
    total = 0
    for code, c in clubs.items():
        h = c["sections"]["history"]["hof"]
        src = by_code[code]
        assert h["live"] is True and h["n"] == src["n"] == len(h["inductees"])
        assert h["n_player_bbwaa"] + h["n_route_unverified"] == h["n"]
        assert [r[0] for r in h["inductees"]] == [rows[i]["name"] for i in src["inductees"]]
        assert {r[4] for r in h["inductees"]} <= {"player_bbwaa", "route_unverified"}
        leaf = _branch(c, "history")["leaves"][-1]
        assert leaf["key"] == "hof" and leaf["kind"] == "count" and leaf["value"] == h["n"]
        assert leaf["link"] == "/hof/"
        total += h["n"]
    assert total + fr["defunct"]["n"] == fr["counts"]["n_credited"] == fr["counts"]["n_inductees"]
    assert "pennants" not in json.dumps(d["clubs"][0]["sections"]["history"]["hof"])


def test_payload_under_size_budget(d):
    assert ART.stat().st_size < 1_500_000
    assert len(json.dumps(d, separators=(",", ":"))) < 1_500_000


# --------------------------------------------------------------------------
# The refusal path (never writes a repo file)
# --------------------------------------------------------------------------

def test_export_refuses_below_thirty_clubs_and_files_ingest_health(tmp_path, monkeypatch):
    import franchise_export as fe
    real = fe._team_rows

    def drop_one(payload, key="teams"):
        rows = real(payload, key)
        if "LAD" in rows and payload.get("teams") and "war_sp" in (payload["teams"][0] or {}):
            rows.pop("LAD")
        return rows
    monkeypatch.setattr(fe, "_team_rows", drop_one)
    monkeypatch.setattr(fe, "OUT", tmp_path / "franchise_board.json")
    with pytest.raises(fe.FranchiseRefusal) as exc:
        fe.build()
    assert "roster" in str(exc.value) and "LAD" in str(exc.value)
    assert fe.main() == 2
    assert not (tmp_path / "franchise_board.json").exists(), "a refusal never writes"
    src = _src("run_monthly.py")
    assert '_record_ingest("franchise_export"' in src and "franchise export refused" in src


# --------------------------------------------------------------------------
# Wiring (the checklist test_mgmt_export enforces for a new module)
# --------------------------------------------------------------------------

def test_franchise_is_in_publish_paths():
    lines = _src("deploy/publish_paths.txt").splitlines()
    assert "franchise" in lines


def test_franchise_is_in_sitemap():
    assert '("/franchise/", "daily", "0.7")' in _src("build_site.py")
    sm = ROOT / "sitemap.xml"
    if sm.exists():
        assert "/franchise/" in sm.read_text(encoding="utf-8")


def test_franchise_is_excluded_from_pytest_collection():
    assert "\n    franchise\n" in _src("pytest.ini")


def test_franchise_is_in_the_data_catalog():
    assert '"franchise_board.json"' in _src("data_catalog.py")
    import data_catalog
    row = next(r for r in data_catalog.catalog_rows() if r["file"] == "franchise_board.json")
    assert row["pinned_by"] == "test_franchise_export.py"


def test_franchise_is_a_watched_scheduled_export():
    src = _src("run_monthly.py")
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_export"' in src[i:i + 3200], "the window scan on mgmt_export must still hold"
    j = src.index(")", src.index('"franchise_export"', i))
    block = src[i:j]
    assert block.index('"mlbstats_windows"') < block.index('"ledger_export"') < block.index('"franchise_export"')
    assert "6b7d. Franchise board" in src


def test_franchise_is_first_in_nav_items_and_the_static_copies():
    import build_site
    grp = next(i for i in build_site.NAV_ITEMS if isinstance(i, dict) and i["group"] == "MLB Modules")
    assert grp["children"][0] == ("franchise", "Franchises", "/franchise/")
    assert build_site.MODULE_STAGE["franchise"][0] == "β"
    assert "not a forecast" in build_site.MODULE_STAGE["franchise"][1]
    for rel in ("prospx/index.html", "collegesavant/index.html", "collegesavant/pitcher_index.html"):
        # The leaves carry a 12 px pixel icon before the label (PX-04/PX-10);
        # the slot order is what this pins, so the icon markup is set aside.
        s = re.sub(r'<svg class="ico"[^>]*>.*?</svg>', "", _src(rel))
        i = s.index('<a href="/franchise/" role="menuitem">Franchises</a>')
        assert i < s.index('<a href="/fa/" role="menuitem">Free Agency</a>'), rel
    assert 'franchise_export.py' in _src("tools/strip_emdashes.py")
    assert '"franchise/index.html"' in _src("tools/strip_emdashes.py")


def test_registry_rows_exist_and_are_descriptive():
    reg = _load("model_registry.json")
    rows = {m["model_id"]: m for m in reg["models"]}
    for mid in ("franchise_index", "franchise_branch_score"):
        m = rows[mid]
        assert m["verdict"] == "unvalidated" and m["eval_artifact"] is None
        assert m["predicts"].startswith("nothing.") and "DESCRIPTIVE" in m["predicts"]
        assert "100 + 10z" in m["predicts"]
    assert "team_win_projections" in rows["franchise_index"]["predicts"]
    import model_registry
    assert not [p for p in model_registry.validate() if "franchise" in p]


def test_back_links_land_on_the_projections_open_cell_and_the_prospx_farm_header():
    assert '/franchise/#team=${encodeURIComponent(r.team)}' in _src("assets/projections.js")
    assert '/franchise/#team=${escapeHtml(org.org)}' in _src("prospx/index.html")


def test_the_glossary_hooks_in_the_payload_resolve(d, clubs):
    g = _load("glossary.json")
    ids = {e["id"] for e in g["entries"]}
    hooks = set()
    for c in list(clubs.values())[:3]:
        for b in c["tree"]["branches"]:
            for lf in b["leaves"]:
                if lf.get("gl"):
                    hooks.add(lf["gl"])
    hooks |= set(re.findall(r'gl\((?:[^()]|\([^()]*\))*?,\s*"([a-z_0-9]+)"\)', JS.read_text(encoding="utf-8")))
    assert hooks
    missing = sorted(h for h in hooks if h not in ids)
    assert not missing, missing
    for slug in ("franchise_index", "franchise_branch_score", "season_record", "locked_pct",
                 "leverage_deploy_plus", "cbt_space", "park_factor", "pythag_pct"):
        assert slug in ids, slug


# --------------------------------------------------------------------------
# Review 2026-09-23: a re-served plus metric takes the ladder /mlbstats/ paints
# it on, and the ARBITRATION tiles agree with /arbitration/#teams
# --------------------------------------------------------------------------

def test_roster_leaf_ladders_are_the_family_mlbstats_applies(clubs):
    """The hub tiers offense_plus, bullpen_plus and friends on the SAME
    EephusTiers family the module paints them on (Offense+ took `z` here and
    `ratio` there, so CHC 110 read 'good' on the hub and 'avg' on /mlbstats/).
    The family is read from mlbstats.js itself: `cls(t.<key>, "<fam>")` for a
    team rollup, or the row's `fmt: <helper>` resolved through vtCell."""
    mlb = _src("assets/mlbstats.js")

    def family_of(key):
        m = re.search(r'cls\(t\.%s, "([a-z]+)"\)' % re.escape(key), mlb)
        if m:
            return m.group(1)
        row = re.search(r'key: "%s"[^\n]*\bfmt: (\w+)' % re.escape(key), mlb)
        assert row, f"/mlbstats/ paints no {key}"
        helper = re.search(r'function %s\([^)]*\) \{ return vtCell\(v, "([a-z]+)"' % row.group(1), mlb)
        assert helper, (key, row.group(1))
        return helper.group(1)

    checked = 0
    for c in clubs.values():
        roster = next(b for b in c["tree"]["branches"] if b["key"] == "roster")
        for lf in roster["leaves"]:
            if lf["kind"] != "idx":
                continue
            fam = family_of(lf["key"])
            assert lf["ladder"] == fam, (c["code"], lf["key"], lf["ladder"], fam)
            checked += 1
    assert checked == 5 * len(clubs)
    assert family_of("offense_plus") == "ratio" and family_of("bullpen_plus") == "z"


def test_arbitration_tiles_agree_with_the_arbitration_page_rule(d, clubs):
    """'Eligible' printed every arbitration.json row incl. pre-arb (LAD 22, of
    which 17 are class 0), and 'Projected cost' summed the CLASS_YEAR tuple
    while /arbitration/#teams summed l[0] regardless of season. Now the split
    is served (n_rows / n_arb / n_pre_arb), the cost sums the board.season
    tuple of every row, and arbitration.js sums that same tuple."""
    arb = _load("arbitration.json")
    season = arb["season"]
    assert season == d["class_year"]
    by = {}
    for r in arb["rows"]:
        if r.get("t"):
            by.setdefault(r["t"], []).append(r)
    for code, c in clubs.items():
        a = c["sections"]["arbitration"]
        rows = by.get(code, [])
        assert a["n_rows"] == len(rows), code
        assert a["n_arb"] == sum(1 for r in rows if int(r.get("c") or 0) >= 1), code
        assert a["n_pre_arb"] == a["n_rows"] - a["n_arb"], code
        page_rule = sum(next((t[1] or 0 for t in (r.get("l") or []) if t[0] == season), 0) for r in rows)
        assert a["proj_2027_usd"] == int(round(page_rule)), (code, a["proj_2027_usd"], page_rule)
        assert "pre-arb" in a["basis"]
    lad = clubs["LAD"]["sections"]["arbitration"]
    assert lad["n_arb"] < lad["n_rows"], "the split is real: LAD carries pre-arb rows"
    js = _src("assets/arbitration.js")
    assert "r.l[li][0] === board.season" in js and "t.next += r.l[0][1]" not in js
    assert "pre-arb minimums" in d["copy"]["arb_cost_sum"]
    branch = next(b for b in clubs["LAD"]["tree"]["branches"] if b["key"] == "arbitration")
    assert branch["leaves"][0]["key"] == "n_arb" and "class 1-4" in branch["leaves"][0]["label"]


def test_the_ledger_tax_floor_flag_rides_the_fin_tile_leaf_and_board(d, clubs):
    lg = _load("ledger_board.json")
    below = set(lg["accountability"]["tax_floor_census"]["below"])
    board = {r["code"]: r for r in d["board"]}
    for code, c in clubs.items():
        tf = c["sections"]["fin"]["tax_floor_2027"]
        assert tf == lg["clubs"][code]["payroll"]["tax_floor_2027"], code
        assert board[code]["tax_floor_below_2027"] == (code in below), code
        lf = next(x for x in _branch(c, "fin")["leaves"] if x["key"] == "tax_payroll_2027")
        assert ("guaranteed 2027 contract AAV" in lf["basis"]) == (code in below), code
        assert (c["sections"]["fin"]["tax_payroll_2027_source"] == "guaranteed_aav") == (code in below), code
    assert d["copy"]["tax_floor_note"] == lg["copy"]["tax_floor_note"]
