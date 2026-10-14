# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The team projection candidates T1, T2 and T3 (TM_3_TEAM_CANDIDATES_DARK;
docs/TEAM_PROJECTIONS_GATE.md section 1), built dark.

What is pinned here:
  - every flag defaults False, and with the flags False the Team Outlook rows
    and the in-season overlay are byte-identical whether or not the frozen
    params and a playing-time ledger exist (nothing served moves);
  - the 2,430-win pin holds under T2 on every season, and the un-budgeted
    wins ride under byYear[].winsFaFit, the one field fa_fit._outlook_wins
    reads, so its per-club input wins are equal with the flag on and off;
  - the pure pieces of T2 (allocate, recenter) and T3 (club_runs, the league
    identity report, park factors) and the constants they pin to their
    sources;
  - model/team_projection/params.json hashes to the DEV freeze record in the
    gate document (the freeze happened once).
Synthetic fixtures throughout: no network, no corpus, no served file written.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

import proj_current as pc
import proj_export as pe
import team_projection as TP

ROOT = Path(__file__).parent
FIRST = pe.FIRST_SEASON
H = pe.HORIZON


# --------------------------------------------------------------------------- #
# flags and pinned constants
# --------------------------------------------------------------------------- #

def test_every_candidate_flag_defaults_false():
    assert pe.TEAM_TALENT_RANGE_LIVE is False
    assert pe.TEAM_PT_BUDGET_LIVE is False
    assert pe.TEAM_RUNS_LIVE is False


def test_constants_pin_to_their_sources():
    """The talent draw's k and clip are the in-season blend's own; the runs
    block's BF per IP and Pythagenpat exponent are the engine's."""
    assert TP.K_PSEUDO_GAMES == pe.CURRENT_PRIOR_PSEUDO_GAMES == pc.TALENT_PSEUDO_GAMES == 40
    import proj_backtest as PB
    assert tuple(TP.TALENT_CLIP) == tuple(pc.TALENT_CLIP) == tuple(PB.TALENT_PCT_CLAMP) == (0.20, 0.80)
    import proj_components as PC
    assert TP.BF_PER_IP == PC.BF_PER_IP
    assert TP.PYTHAGENPAT_EXP == pe._PYTHAGENPAT_EXP == PB.PYTHAGENPAT_EXP
    assert len(TP.ORG_NICKNAMES) == 30
    assert set(TP.ORG_NICKNAMES) == {o for members in pc._DIVISIONS.values() for o in members}


def test_talent_sd_is_sigma_t_shrunk_by_games_played_as_a_win_rate():
    assert TP.talent_sd_pct(0.0, 0) == 0.0
    assert TP.talent_sd_pct(None, 50) == 0.0
    assert TP.talent_sd_pct(8.1, 0) == pytest.approx(8.1 / 162.0)
    assert TP.talent_sd_pct(8.1, 40) == pytest.approx(8.1 * 0.5 / 162.0)
    assert TP.talent_sd_pct(8.1, 120) == pytest.approx(8.1 * 40 / 160 / 162.0)
    assert TP.clip_talent(0.05) == 0.20 and TP.clip_talent(0.95) == 0.80 and TP.clip_talent(0.5) == 0.5
    assert TP.sigma_t(10.0, 6.0) == pytest.approx(8.0)
    assert TP.sigma_t(5.0, 6.0) == 0.0


# --------------------------------------------------------------------------- #
# T2: allocate, recenter
# --------------------------------------------------------------------------- #

def test_allocate_scales_pro_rata_over_budget_and_fills_a_shortfall_at_zero_war():
    over = TP.allocate([{"pt": 600, "war": 3.0}, {"pt": 600, "war": 1.0}], 900)
    assert over["scale"] == pytest.approx(0.75)
    assert over["war"] == pytest.approx(3.0)            # 4.0 x 0.75
    assert over["war_unscaled"] == pytest.approx(4.0)
    assert over["shortfall"] == 0.0 and over["pt_allocated"] == 900.0
    under = TP.allocate([{"pt": 300, "war": 2.0}], 900)
    assert under["scale"] == 1.0 and under["war"] == 2.0 and under["shortfall"] == 600.0
    empty = TP.allocate([], 900)
    assert empty["war"] == 0.0 and empty["shortfall"] == 900.0 and empty["scale"] == 1.0


def test_recenter_pins_the_league_to_2430():
    raw = {f"T{i}": 70.0 + i for i in range(30)}
    rec, shift = TP.recenter(raw)
    assert sum(rec.values()) == pytest.approx(2430.0)
    assert shift == pytest.approx((2430.0 - sum(raw.values())) / 30)
    assert TP.recenter({}) == ({}, 0.0)


# --------------------------------------------------------------------------- #
# T3: club runs, the league identity, park factors
# --------------------------------------------------------------------------- #

def _runs_fixture(lg_runs=720.0, pf=None):
    clubs = {}
    orgs = sorted(TP.ORG_NICKNAMES)
    # zero-sum components: +x for half the league, -x for the other half
    for i, o in enumerate(orgs):
        sgn = 1.0 if i % 2 == 0 else -1.0
        clubs[o] = TP.club_runs(lg_runs, sgn * 30.0, sgn * 20.0, sgn * 5.0,
                                (pf or {}).get(o, 1.0))
    return clubs


def test_rs_and_ra_sum_to_the_league_total_on_zero_sum_components():
    lg = 720.0
    clubs = _runs_fixture(lg)
    rep = TP.runs_identity(clubs, lg)
    assert rep["n_clubs"] == 30
    assert rep["rs_sum"] == pytest.approx(30 * lg, abs=0.5)
    assert rep["ra_sum"] == pytest.approx(30 * lg, abs=0.5)
    assert rep["within_tol"] is True
    assert rep["tol_runs"] == pytest.approx(30 * lg * TP.RUNS_IDENTITY_TOL, abs=0.1)
    # the report never enforces: an off-identity league is named, not fixed
    skew = {o: dict(v, rs=v["rs"] + 40.0) for o, v in clubs.items()}
    assert TP.runs_identity(skew, lg)["within_tol"] is False


def test_club_runs_is_pythagenpat_at_the_team_level_with_the_park_factor_on_both_sides():
    line = TP.club_runs(700.0, 0.0, 0.0, 0.0, 1.0)
    assert line["rs"] == line["ra"] == 700.0 and line["pythW"] == 81.0 and line["runDiff"] == 0.0
    good = TP.club_runs(700.0, 40.0, 30.0, 10.0, 1.0)
    assert good["rs"] == 740.0 and good["ra"] == 660.0 and good["runDiff"] == 80.0
    assert good["pythW"] == pytest.approx(TP.pythag_wins(740.0, 660.0), abs=0.05)
    assert good["pythW"] > 81.0
    park = TP.club_runs(700.0, 40.0, 30.0, 10.0, 1.10)
    assert park["rs"] == pytest.approx(740.0 * 1.10, abs=0.05)
    assert park["ra"] == pytest.approx(660.0 * 1.10, abs=0.05)
    assert park["pythW"] == pytest.approx(good["pythW"], abs=0.5)   # a park moves runs, not wins (much)
    assert TP.pythag_wins(None, 600) is None and TP.pythag_wins(0, 0) is None
    # the engine's own form (proj_export._pythag_pct with games known)
    assert TP.pythag_wins(740.0, 660.0) == pytest.approx(162 * pe._pythag_pct(740.0, 660.0, 162), abs=1e-9)


def test_component_runs_reads_the_heads_line_and_names_what_is_not_projected():
    hit = {"lines": {1: {"pa": 600.0, "bat": 12.0, "bsr": 3.0, "fld": -4.0}}}
    cr = TP.component_runs(hit, "hit", 0.5, 1)
    assert cr["bat_bsr"] == pytest.approx(7.5) and cr["fld"] == pytest.approx(-2.0)
    assert cr["pt"] == 300.0 and cr["not_projected"] == []
    pit = {"lines": {1: {"ip": 180.0, "fip_runs_100ip": 8.0}}}
    cp = TP.component_runs(pit, "pit", 1.0, 1)
    assert cp["fip_raa"] == pytest.approx(14.4) and cp["pt"] == 180.0
    none = TP.component_runs(None, "pit")
    assert none["fip_raa"] == 0.0 and none["not_projected"] == ["pit:no_block"]
    partial = TP.component_runs({"lines": {1: {"pa": 500.0, "bat": None, "bsr": 1.0, "fld": None}}}, "hit")
    assert set(partial["not_projected"]) == {"hit:bat", "hit:fld"} and partial["bat_bsr"] == 1.0


def test_park_factors_read_the_cache_and_fall_back_to_neutral_by_name(tmp_path):
    rows = [{"Season": 2025, "Team": TP.ORG_NICKNAMES[o], "Basic (5yr)": 100.0 + i}
            for i, o in enumerate(sorted(TP.ORG_NICKNAMES)) if o != "COL"]
    rows.append({"Season": 2025, "Team": "Indians", "Basic (5yr)": 97.0})   # a renamed club
    (tmp_path / "park_factors_2025.json").write_text(json.dumps({"complete": True, "rows": rows}))
    (tmp_path / "park_factors_2026.json").write_text(json.dumps({"complete": False, "rows": []}))
    pf, meta = TP.park_factors(2026, tmp_path)
    assert meta["season_used"] == 2025 and meta["file"] == "park_factors_2025.json"
    assert meta["neutral_fallback"] == ["COL"] and pf["COL"] == 1.0
    assert pf["ARI"] == pytest.approx(1.0) and pf["WSN"] == pytest.approx(1.29)
    assert len(pf) == 30
    none, meta2 = TP.park_factors(2010, tmp_path)
    assert meta2["season_used"] is None and all(v == 1.0 for v in none.values())


def test_the_served_park_factor_cache_names_every_club():
    p = TP.PARK_FACTOR_DIR / "park_factors_2025.json"
    if not p.exists():
        pytest.skip("no park factor cache on this machine")
    pf, meta = TP.park_factors(2025)
    assert meta["neutral_fallback"] == [], meta
    assert len(pf) == 30


# --------------------------------------------------------------------------- #
# the roll-up with the flags off and on
# --------------------------------------------------------------------------- #

def _league_fixture():
    """30 clubs, one controlled hitter and one controlled pitcher each, with
    two clubs over the PA budget and three over the IP budget."""
    orgs = sorted(TP.ORG_NICKNAMES)
    vets, ledger = [], {}
    mlbam = 100000
    for i, o in enumerate(orgs):
        for side, pos in (("hit", "SS"), ("pit", "SP")):
            mlbam += 1
            w = 2.0 + (i % 7) * 0.5
            champ = [round(w - 0.3 * t, 2) for t in range(H)]
            m = {"mlbam": mlbam, "name": f"{o} {side}", "key": f"{o}-{side}", "team": o,
                 "pos": pos, "age": 27, "src": "vet", "thru": FIRST + H - 1,
                 "war": champ, "warChamp": champ, "warY1Champ": champ[0]}
            vets.append(m)
            if side == "hit":
                pt = [7000.0] * H if i < 2 else [5500.0] * H
            else:
                pt = [1600.0 * TP.BF_PER_IP] * H if i < 3 else [1300.0 * TP.BF_PER_IP] * H
            ledger[(mlbam, side)] = {"mlbam": mlbam, "side": side, "src": "vet", "team": o,
                                     "last_ctrl": FIRST + H - 1, "age": 27, "role": pos,
                                     "pt": pt, "war": champ, "hist": []}
    prospects = [{"team": orgs[0], "eta": FIRST, "war": [1.0] * H, "name": "P", "key": "p"},
                 {"team": orgs[5], "eta": FIRST + 2, "war": [1.5] * H, "name": "Q", "key": "q"}]
    depth = {o: [1.0 + 0.1 * (i % 3)] * H for i, o in enumerate(orgs)}
    return vets, prospects, depth, ledger


@pytest.fixture
def quiet_outlook(monkeypatch):
    """No served file is written and no farm join is read by the roll-up."""
    monkeypatch.setattr(pe, "_write_team_outlook_eval", lambda *a, **k: None)
    monkeypatch.setattr(pe, "_org_farm_blocks", lambda: {})
    pe._TEAM_PREVIEW.clear()
    yield
    pe._TEAM_PREVIEW.clear()


BUDGET = {"pa": 6096.7, "ip": 1436.4}
CANDIDATE_KEYS = ("winsFaFit", "ptBudget", "runs")


def test_team_outlook_is_byte_identical_with_the_flags_off(quiet_outlook):
    vets, prospects, depth, ledger = _league_fixture()
    base = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                            pt_ledger={}, budget=None, live=False)
    dark = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                            pt_ledger=ledger, budget=BUDGET, live=False)
    assert json.dumps(base, sort_keys=True) == json.dumps(dark, sort_keys=True)
    for r in dark:
        assert not any(k in r for k in CANDIDATE_KEYS), r["team"]
        assert not any("winsFaFit" in b for b in r["byYear"]), r["team"]
    # the candidate was still computed, to the preview only
    assert pe._TEAM_PREVIEW["budget"]["status"] == "preview"
    assert len(pe._TEAM_PREVIEW["budget"]["clubs"]) == 30


def test_the_budget_keeps_the_2430_pin_and_the_fa_fit_field_on_every_season(quiet_outlook):
    vets, prospects, depth, ledger = _league_fixture()
    off = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                           pt_ledger=ledger, budget=BUDGET, live=False)
    on = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                          pt_ledger=ledger, budget=BUDGET, live=True)
    off_by = {r["team"]: r["byYear"] for r in off}
    on_by = {r["team"]: r["byYear"] for r in on}
    assert set(off_by) == set(on_by) == set(TP.ORG_NICKNAMES)
    for t in range(H):
        # the pin is exact before the 0.1 rounding of each club (30 x 0.05 at most),
        # the same tolerance the served guard test_league_wins_sum_to_2430 allows
        assert sum(on_by[o][t]["wins"] for o in on_by) == pytest.approx(2430.0, abs=1.6)
        for o in on_by:
            b = on_by[o][t]
            assert b["wins"] + b["losses"] == pytest.approx(162.0, abs=0.11)
            # THE FA FIT FIELD: the un-budgeted wins of this same frame, exactly
            assert b["winsFaFit"] == off_by[o][t]["wins"], (o, t)
            # the player roll-up (war, winsRaw, n) never moves with the budget
            for k in ("war", "winsRaw", "n", "season"):
                assert b[k] == off_by[o][t][k], (o, t, k)
    # the top-level mirrors follow byYear[0]
    for r in on:
        assert r["wins"] == r["byYear"][0]["wins"] and r["ptBudget"]["paScale"] <= 1.0
    scaled = [r["team"] for r in on if r["ptBudget"]["paScale"] < 1.0]
    assert len(scaled) == 2
    assert sum(1 for r in on if r["ptBudget"]["ipScale"] < 1.0) == 3
    # a club over budget carries less WAR than its un-budgeted sum; one under it carries the same
    over = next(r for r in on if r["team"] == scaled[0])
    assert over["ptBudget"]["warBudget"] < over["ptBudget"]["warUnscaled"]
    under = next(r for r in on if r["ptBudget"]["paScale"] == 1.0 and r["ptBudget"]["ipScale"] == 1.0)
    assert under["ptBudget"]["warBudget"] == pytest.approx(under["ptBudget"]["warUnscaled"])
    # the budgeted wins differ from the served ones somewhere (the candidate is a candidate)
    assert any(on_by[o][0]["wins"] != off_by[o][0]["wins"] for o in on_by)


def test_fa_fit_reads_the_same_wins_with_the_budget_on_and_off(quiet_outlook, tmp_path, monkeypatch):
    """R4 (gate section 6.2): fa_fit._outlook_wins's per-club, per-year input
    wins are equal before and after the repoint on the same inputs, so
    data/fa_class.json cannot move with TEAM_PT_BUDGET_LIVE."""
    import fa_fit
    vets, prospects, depth, ledger = _league_fixture()
    off = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                           pt_ledger=ledger, budget=BUDGET, live=False)
    on = pe._team_outlook(copy.deepcopy(vets), copy.deepcopy(prospects), depth, {}, {},
                          pt_ledger=ledger, budget=BUDGET, live=True)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(fa_fit, "__file__", str(tmp_path / "fa_fit.py"))
    got = {}
    for name, rows in (("off", off), ("on", on)):
        (tmp_path / "data" / "mlb_projections.json").write_text(
            json.dumps({"team_outlook": rows}), encoding="utf-8")
        fa_fit._outlook_wins.cache_clear()
        got[name] = {y: fa_fit._outlook_wins(y) for y in range(FIRST, FIRST + H)}
    fa_fit._outlook_wins.cache_clear()
    for y in range(FIRST, FIRST + H):
        assert len(got["off"][y]) == 30
        assert got["on"][y] == got["off"][y], y
        # and the field is the un-budgeted total, not the served headline under the flag
        headline_on = {r["team"]: float(r["byYear"][y - FIRST]["wins"]) for r in on}
        assert got["on"][y] != headline_on


def test_the_overlay_consumes_the_same_draws_with_the_talent_flag_off(monkeypatch):
    """With TEAM_TALENT_RANGE_LIVE False the served odds are the incumbent
    call's own numbers whether or not a frozen sigma_T exists; the candidate
    goes to the preview only."""
    monkeypatch.setattr(pc, "remaining_schedule", lambda season, today=None, played=None: {})
    monkeypatch.setattr(pc, "remaining_pairs", lambda season, today=None: [])
    import datetime as _dt
    orgs = sorted(TP.ORG_NICKNAMES)
    div_of = {o: dv for dv, members in pc._DIVISIONS.items() for o in members}
    standings = {o: {"wins": 50 + i % 9, "losses": 45 + (i * 3) % 7, "pct": None, "gamesPlayed": None,
                     "rs": 450 + i, "ra": 440 + (i * 5) % 30, "runDiff": 0, "divGb": 0.0,
                     "league": 103 if div_of[o].startswith("AL") else 104, "div": div_of[o],
                     "pythagWins": None, "pythagLosses": None}
                 for i, o in enumerate(orgs)}
    for s in standings.values():
        s["gamesPlayed"] = s["wins"] + s["losses"]
        s["pct"] = round(s["wins"] / s["gamesPlayed"], 3)

    def rows():
        return [{"team": o, "war": 10.0, "wins": 70.0 + i, "losses": 92.0 - i, "winsRaw": 70.0 + i,
                 "depthWar": 1.0, "n": 20, "byYear": [], "top": [], "farm": None}
                for i, o in enumerate(orgs)]

    def run(params):
        monkeypatch.setattr(pe, "_team_params", lambda: params)
        pe._TEAM_PREVIEW.clear()
        r = rows()
        pe._attach_current_season(r, standings, season=FIRST - 1, today=_dt.date(FIRST - 1, 7, 15))
        return r

    base = run(None)
    with_sigma = run({"sigma_T": 7.6765, "budget": BUDGET})
    assert json.dumps(base, sort_keys=True) == json.dumps(with_sigma, sort_keys=True)
    assert all(r["current"]["wsPct"] is not None for r in base)
    prev = pe._TEAM_PREVIEW.get("talent_range")
    assert prev and prev["status"] == "preview" and prev["sigma_T"] == 7.6765
    assert len(prev["clubs"]) == 30
    # the candidate widens the band at a fixed talent point: wider P10-P90 on average
    width = lambda c: [c[o]["projWinsP90"] - c[o]["projWinsP10"] for o in c]
    cand_w = sum(width(prev["clubs"])) / 30
    inc_w = sum((prev["clubs"][o]["incumbent"]["projWinsP90"] - prev["clubs"][o]["incumbent"]["projWinsP10"])
                for o in prev["clubs"]) / 30
    assert cand_w > inc_w
    pe._TEAM_PREVIEW.clear()


def test_build_futures_does_not_read_the_candidates():
    """The futures board is built from `current` alone, so with the flag off it
    is the same file apart from its timestamp."""
    import inspect
    src = inspect.getsource(pe.build_futures)
    assert "TEAM_TALENT_RANGE_LIVE" not in src and "_team_params" not in src


def test_write_preview_lands_under_the_named_path_only(tmp_path):
    p = TP.write_preview({"a": 1}, tmp_path / "preview" / "x.json")
    assert p.exists() and json.loads(p.read_text())["a"] == 1
    assert "written_at" in json.loads(p.read_text())
    assert TP.PREVIEW_DIR == ROOT / ".cache" / "team_projection" / "preview"


# --------------------------------------------------------------------------- #
# the DEV freeze
# --------------------------------------------------------------------------- #

def test_params_hash_is_independent_of_formatting():
    a = {"b": [1, 2], "a": {"y": 1.5, "x": "s"}}
    assert TP.params_hash(a) == TP.params_hash(json.loads(json.dumps(a, indent=3)))
    assert len(TP.params_hash(a)) == 64


def test_params_json_hashes_to_the_gate_record_and_the_receipt():
    """DEV is frozen once: model/team_projection/params.json hashes to the
    'DEV frozen <date> at <sha>, params sha256 <hash>' entry of
    docs/TEAM_PROJECTIONS_GATE.md section 8, and the receipt beside it names
    the same hash."""
    params = TP.load_params()
    assert params is not None, "model/team_projection/params.json is absent"
    doc = (ROOT / "docs" / "TEAM_PROJECTIONS_GATE.md").read_text(encoding="utf-8")
    recorded = re.findall(r"DEV frozen \d{4}-\d{2}-\d{2} at [0-9a-f]{7,40}, params sha256 ([0-9a-f]{64})", doc)
    assert len(recorded) == 1, "exactly one DEV freeze entry"
    assert TP.params_hash(params) == recorded[0]
    TP.check_params(params, recorded[0])
    receipt = json.loads(TP.DEV_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["params_sha256"] == recorded[0]
    with pytest.raises(TP.TeamParamsError):
        TP.check_params(params, "0" * 64)


def test_the_frozen_constants_have_the_registered_form():
    p = TP.load_params()
    assert p is not None
    assert p["dev_seasons"] == [2022, 2023, 2024, 2025] and 2026 not in p["dev_seasons"]
    assert p["aging"] == "v2"
    assert p["sigma_T"] == pytest.approx(TP.sigma_t(p["s_res"], p["s_sched"]), abs=1e-3)
    assert p["k_pseudo_games"] == TP.K_PSEUDO_GAMES and p["talent_clip"] == list(TP.TALENT_CLIP)
    assert 5500 < p["budget"]["pa"] < 6600 and 1350 < p["budget"]["ip"] < 1500
    assert p["sim"]["n_sims"] == pc.MC_SIMS and p["sim"]["seed"] == pc.MC_SEED
    assert p["runs"]["park_factor_column"] == TP.PF_COLUMN
