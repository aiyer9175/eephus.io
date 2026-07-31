# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Offline tests for the positional-conversion stack.

Nothing here touches the network. The ingest modules are exercised against
literal CSV/JSON fixtures; the model is exercised against synthetic data with a
known answer, and then against the committed data/positional_fit.json payload.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fielding_innings as fi
import positional_fit as pf
import savant_oaa as so

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "data" / "positional_fit.json"

OAA_CSV = (
    '"last_name, first_name","player_id","display_team_name","year",'
    '"primary_pos_formatted","fielding_runs_prevented","outs_above_average",'
    '"outs_above_average_infront","outs_above_average_lateral_toward3bline",'
    '"outs_above_average_lateral_toward1bline","outs_above_average_behind",'
    '"outs_above_average_rhh","outs_above_average_lhh",'
    '"actual_success_rate_formatted","adj_estimated_success_rate_formatted",'
    '"diff_success_rate_formatted"\n'
    '"Abrams, CJ","682928","Nationals","","SS","-14",-18,-6,-6,-6,0,-10,-8,'
    '"73%","76%","-3%"\n'
    '"Adames, Willy","642715","Brewers","","SS","0",1,4,3,-6,0,-1,1,'
    '"68%","68%","0%"\n')


# ------------------------------------------------------------------- ingest
def test_parse_rows_stamps_year_even_when_the_column_is_empty():
    """Savant returns an EMPTY year column under some parameter combinations.
    Trusting it produces undated rows, so the year is stamped by us."""
    rows = so.parse_rows(OAA_CSV, 2024, "SS")
    assert len(rows) == 2
    assert {r["season"] for r in rows} == {2024}
    assert {r["pos"] for r in rows} == {"SS"}
    a = rows[0]
    assert a["mlbam"] == 682928
    assert a["oaa"] == -18.0 and a["frp"] == -14.0
    assert a["l3"] == -6.0 and a["bk"] == 0.0
    assert a["sr_act"] == pytest.approx(0.73)
    assert a["sr_exp"] == pytest.approx(0.76)


def test_parse_rows_is_fail_soft_on_junk():
    assert so.parse_rows("", 2024, "SS") == []
    assert so.parse_rows("not,a,leaderboard\n1,2,3\n", 2024, "SS") == []


def test_fetch_raw_never_raises_and_falls_back(monkeypatch, tmp_path):
    """A network failure with no cache must return an empty string, not blow up
    the nightly build."""
    monkeypatch.setattr(so, "CACHE_DIR", tmp_path / "nope")

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(so.urllib.request, "urlopen", boom)
    assert so.fetch_raw(1999, 6, force=True) == ""


def test_innings_are_baseball_thirds_not_decimals():
    """'12.2' is twelve and two thirds. Reading it as 12.2 silently biases every
    per-inning rate the model computes."""
    assert fi.innings_to_float("12.2") == pytest.approx(12 + 2 / 3)
    assert fi.innings_to_float("12.1") == pytest.approx(12 + 1 / 3)
    assert fi.innings_to_float("12.0") == pytest.approx(12.0)
    assert fi.innings_to_float("") == 0.0
    assert fi.innings_to_float(None) == 0.0


def test_parse_season_sums_stints_and_converts_innings():
    doc = {"stats": [{"splits": [
        {"player": {"id": 1}, "position": {"abbreviation": "SS"},
         "stat": {"games": 10, "gamesStarted": 9, "innings": "80.1"}},
        {"player": {"id": 1}, "position": {"abbreviation": "SS"},
         "stat": {"games": 5, "gamesStarted": 5, "innings": "40.2"}},
        {"player": {"id": 1}, "position": {"abbreviation": "2B"},
         "stat": {"games": 3, "gamesStarted": 2, "innings": "20.0"}},
    ]}]}
    out = fi.parse_season(doc)
    assert out["1"]["SS"]["g"] == 15 and out["1"]["SS"]["gs"] == 14
    assert out["1"]["SS"]["inn"] == pytest.approx(121.0, abs=0.05)
    assert out["1"]["2B"]["inn"] == pytest.approx(20.0)


# -------------------------------------------------------------------- model
def test_solve_D_recovers_a_known_difficulty_vector():
    """The difficulty solver is the load-bearing estimator. Feed it pairs
    generated from a known D and it must return that D up to the sum-zero
    normalisation."""
    truth = {"1B": 3.0, "2B": 0.0, "3B": 2.0, "SS": -3.0,
             "LF": -1.0, "CF": -1.5, "RF": 0.5}
    truth = {k: v - sum(truth.values()) / len(truth) for k, v in truth.items()}
    pairs = []
    for a in pf.OAA_POSITIONS:
        for b in pf.OAA_POSITIONS:
            if a >= b:
                continue
            for _ in range(40):
                pairs.append((a, b, truth[b] - truth[a], 500.0))
    beta = pf._solve_D(pairs)
    for p in pf.OAA_POSITIONS:
        assert beta[pf.IDX[p]] == pytest.approx(truth[p], abs=0.05)


def test_shrunk_z_shrinks_toward_league_average():
    """Identical raw rates must produce different beliefs at different exposures,
    and an equal number of innings at 1B must be trusted LESS than at SS, because
    the first-base signal is weaker relative to its noise. (Note this is about the
    shrinkage FRACTION and the resulting error bar, not about the level: minus
    eight runs per 1000 innings at first base does imply a more extreme glove than
    the same rate at short, because the first-base spread is narrower.)"""
    sig = {p: {"signal_sd": 4.0, "k_inn": 1000.0} for p in pf.OAA_POSITIONS}
    sig["1B"] = {"signal_sd": 2.33, "k_inn": 2539.0}
    sig["SS"] = {"signal_sd": 5.49, "k_inn": 874.0}
    D = {p: 0.0 for p in pf.OAA_POSITIONS}

    small, se_small = pf._shrunk_z({"SS": {"rate": -8.0, "inn": 100.0}}, D, sig)
    big, se_big = pf._shrunk_z({"SS": {"rate": -8.0, "inn": 1300.0}}, D, sig)
    assert abs(small) < abs(big) < 8.0 / 5.49
    assert se_small > se_big
    # more evidence never makes the estimate less certain
    both, se_both = pf._shrunk_z(
        {"SS": {"rate": -8.0, "inn": 1300.0}, "2B": {"rate": -8.0, "inn": 600.0}},
        D, sig)
    assert se_both < se_big

    at_1b, se_1b = pf._shrunk_z({"1B": {"rate": -8.0, "inn": 900.0}}, D, sig)
    at_ss, se_ss = pf._shrunk_z({"SS": {"rate": -8.0, "inn": 900.0}}, D, sig)
    assert se_1b > se_ss                    # the same innings buy less certainty
    frac_1b = abs(at_1b) / (8.0 / sig["1B"]["signal_sd"])
    frac_ss = abs(at_ss) / (8.0 / sig["SS"]["signal_sd"])
    assert frac_1b < frac_ss                # and are shrunk harder toward average


def test_zero_evidence_gives_exactly_league_average():
    sig = {p: {"signal_sd": 4.0, "k_inn": 1000.0} for p in pf.OAA_POSITIONS}
    z, se = pf._shrunk_z({}, {p: 0.0 for p in pf.OAA_POSITIONS}, sig)
    assert z == 0.0 and se == 1.0


def test_auc_matches_hand_computed_values():
    assert pf._auc([1, 2, 3, 4], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert pf._auc([4, 3, 2, 1], [0, 0, 1, 1]) == pytest.approx(0.0)
    assert pf._auc([1, 1, 1, 1], [0, 0, 1, 1]) == pytest.approx(0.5)
    assert pf._auc([1, 2, 3], [0, 0, 0]) is None


# ---------------------------------------------------------- payload contract
@pytest.fixture(scope="module")
def payload():
    if not PAYLOAD.exists():
        pytest.skip("data/positional_fit.json not built")
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_payload_has_the_documented_blocks(payload):
    for k in ("model", "target_season", "fit", "validation", "conversion_accuracy",
              "players", "top_demotions", "top_promotions", "caveats"):
        assert k in payload, k
    for k in ("ladder", "signal", "difficulty", "feasibility",
              "conversion_matrix", "interaction_check", "aging"):
        assert k in payload["fit"], k


def test_ladder_is_a_real_inversion_not_a_guess(payload):
    L = payload["fit"]["ladder"]
    assert L["r2"] > 0.95
    assert L["n_player_seasons"] > 5000
    v = L["values"]
    # the defensive spectrum must come out in the right order
    assert v["C"] > v["SS"] > v["2B"] > v["3B"] > v["1B"] > v["DH"]
    assert v["CF"] > v["RF"] and v["CF"] > v["LF"]
    assert v["LF"] < 0 and v["RF"] < 0
    # every rung must be inside its own bootstrap interval
    for p, val in v.items():
        lo, hi = L["ci95"][p]
        assert lo <= val <= hi, p


def test_ladder_disagrees_with_the_folklore_table_where_it_matters(payload):
    """The whole point of re-estimating: the hard-coded table over-penalises 1B
    and DH by nearly four runs and treats 2B/3B/CF as one rung."""
    L = payload["fit"]["ladder"]
    v, s = L["values"], L["folklore_ladder"]
    assert v["1B"] - s["1B"] > 3.0
    assert v["DH"] - s["DH"] > 3.0
    assert v["2B"] - v["3B"] > 0.75          # folklore says these are equal
    assert abs(v["LF"] - v["RF"]) < 0.5      # folklore is right that these are not


def test_difficulty_is_measured_above_its_own_permutation_null(payload):
    """SS and 1B are the two rungs the conversion model leans on hardest, so
    both must clear the label-shuffle null."""
    Dd = payload["fit"]["difficulty"]
    for p in ("SS", "1B"):
        assert abs(Dd["values"][p]) > Dd["perm_null95"][p], p
    assert Dd["values"]["SS"] < 0 < Dd["values"]["1B"]
    assert Dd["n_pairs"] > 1000


def test_signal_sd_ranks_the_positions_the_way_the_spectrum_does(payload):
    """How much a glove is WORTH is what makes a move player-specific. If this
    ordering ever inverts, every demotion recommendation flips sign."""
    S = payload["fit"]["signal"]
    assert S["SS"]["signal_sd"] > S["2B"]["signal_sd"] > S["1B"]["signal_sd"]
    assert S["CF"]["signal_sd"] > S["LF"]["signal_sd"]
    assert S["1B"]["k_inn"] > S["SS"]["k_inn"]      # 1B is the least reliable read
    for p, v in S.items():
        assert 0.0 < v["signal_sd"] < v["obs_sd"], p


def test_conversion_matrix_is_antisymmetric(payload):
    M = payload["fit"]["conversion_matrix"]
    for a in pf.OAA_POSITIONS:
        for b in pf.OAA_POSITIONS:
            fwd = M[a][b]["net_for_average_glove_per_650pa"]
            rev = M[b][a]["net_for_average_glove_per_650pa"]
            assert fwd == pytest.approx(-rev, abs=0.05), (a, b)
        assert M[a][a]["net_for_average_glove_per_650pa"] == pytest.approx(0.0, abs=0.02)


def test_feasibility_never_offers_an_uphill_move(payload):
    """The identifying variation only covers players who could already play both
    spots. Offering a random left fielder shortstop is the failure mode this
    guard exists to prevent."""
    F = payload["fit"]["feasibility"]
    lad = payload["fit"]["ladder"]["values"]
    for a, allowed in F["allowed"].items():
        for b in allowed:
            if b in (a, "DH"):
                continue
            assert lad[b] <= lad[a] + F["ladder_tolerance_runs"], (a, b)
    assert F["allowed"]["1B"] == ["1B", "DH"]
    assert "SS" not in F["allowed"]["LF"]
    assert "CF" not in F["allowed"]["LF"]


def test_every_player_row_is_internally_consistent(payload):
    lad = payload["fit"]["ladder"]["values"]
    for r in payload["players"]:
        for p, v in r["by_position"].items():
            assert v["ladder"] == pytest.approx(lad[p])
            assert v["def_total"] == pytest.approx(v["field"] + v["ladder"], abs=0.02)
        assert r["by_position"]["DH"]["field"] == 0.0
        if r["best_pos"]:
            best = max(r["by_position"],
                       key=lambda p: r["by_position"][p]["def_total"])
            assert r["best_pos"] == best
        cur = r["current_pos"]
        if r["gain_runs_per_650"] is not None and cur in r["by_position"]:
            expect = (r["by_position"][r["best_pos"]]["def_total"]
                      - r["by_position"][cur]["def_total"])
            assert r["gain_runs_per_650"] == pytest.approx(expect, abs=0.02)
        if r["demotion_gain"] is not None:
            assert r["demotion_gain_player_part"] + r["demotion_gain_league_part"] \
                == pytest.approx(r["demotion_gain"], abs=0.02)
            assert lad[r["demotion_pos"]] < lad[cur]


def test_a_flag_requires_both_a_size_and_a_signal_to_noise_bar(payload):
    rule = payload["flag_rule"]
    for r in payload["players"]:
        if r["flagged_misplaced"]:
            assert r["gain_runs_per_650"] >= rule["min_gain_runs_per_650"]
            assert r["gain_runs_per_650"] >= rule["min_sigma"] * r["gain_se"]
            assert not r["c_out_of_scope"]
        if r["flagged_demotion"]:
            assert r["demotion_gain"] >= rule["min_gain_runs_per_650"]
            assert r["demotion_gain"] >= rule["min_sigma"] * r["demotion_se"]


def test_catchers_are_never_offered_a_move(payload):
    cs = [r for r in payload["players"] if r["c_out_of_scope"]]
    assert cs, "no catchers in the universe at all is itself a bug"
    for r in cs:
        assert r["best_pos"] is None
        assert r["demotion_pos"] is None
        assert not r["flagged_misplaced"] and not r["flagged_demotion"]


def test_headline_lists_are_regulars_only(payload):
    """A backup with 120 innings has a glove estimate that is almost all prior, so
    his 'gain' is a statement about the ladder, not about him."""
    rule = payload["flag_rule"]
    by_id = {r["mlbam"]: r for r in payload["players"]}
    for key in ("top_demotions", "top_promotions"):
        assert len(payload[key]) <= 40
        for r in payload[key]:
            full = by_id[r["mlbam"]]
            assert full["qualified"], full["name"]
            innings = sum(full["innings"].values())
            assert ((full["pa"] or 0) >= rule["headline_min_pa"]
                    or innings >= rule["headline_min_innings"]), full["name"]
    for r in payload["top_demotions"]:
        assert r["demotion_gain"] >= rule["min_gain_runs_per_650"]
    order = [r["demotion_gain"] for r in payload["top_demotions"]]
    assert order == sorted(order, reverse=True)


def test_conversion_model_beats_carry_over_and_the_zero_information_control(payload):
    """The model's actual claim is 'here is his rate at the new position'. This
    is the measurement that claim rests on."""
    C = payload["conversion_accuracy"]
    assert C["n_conversions"] >= 100
    assert C["mae"]["model"] < C["mae"]["carry_over"]
    adv = C["mae_advantage_over"]
    assert adv["carry_over"]["beats"], adv["carry_over"]
    assert adv["permuted"]["beats"], adv["permuted"]
    # the advantage must sit outside the permutation null, not merely above zero
    assert adv["carry_over"]["mean"] > C["perm_null95_mae_advantage"]
    assert C["n_time_splits"] >= 4


def test_demotion_discrimination_is_recorded_as_the_null_it_is(payload):
    """This lane did NOT beat raw OAA at predicting who gets demoted. The test
    pins that honest result so a future change cannot quietly claim otherwise
    without updating it."""
    V = payload["validation"]
    assert V["auc"]["raw_oaa"] > V["auc"]["model"]
    assert abs(V["auc"]["model"] - 0.5) <= V["perm_null95_auc_minus_half"]
    assert V["n_time_splits"] >= 4


def test_interaction_check_records_its_verdict(payload):
    I = payload["fit"]["interaction_check"]
    assert I["n_moves"] >= 8
    assert I["n_predicted_inside_ci"] >= I["n_moves"] // 2
    for r in I["rows"]:
        assert r["observed_slope"] < 0     # noise alone forces this sign


def test_no_em_or_en_dashes_in_any_shipped_string(payload):
    """Owner rule, enforced by the copy gate elsewhere in the repo."""
    bad = [c for c in ("—", "–") ]
    blob = json.dumps(payload, ensure_ascii=False)
    for ch in bad:
        assert ch not in blob, f"dash {ch!r} in positional_fit.json"
    for mod in (pf, so, fi):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for ch in bad:
            assert ch not in src, f"dash {ch!r} in {mod.__name__}"


def test_arozarena_case_is_stable(payload):
    """The owner's named example. He should be a below-average corner outfielder
    whose best feasible spot is lower on the ladder than left field."""
    row = next((r for r in payload["players"] if r["mlbam"] == 668227), None)
    if row is None:
        pytest.skip("Arozarena not in the target-season universe")
    lad = payload["fit"]["ladder"]["values"]
    assert row["glove_z"] < 0
    assert row["current_pos"] in ("LF", "RF")
    assert row["best_pos"] is not None
    assert lad[row["best_pos"]] <= lad[row["current_pos"]]
    ev = [e for e in row["evidence"] if e["pos"] in ("LF", "RF")]
    assert ev and all(e["inn"] > 0 for e in ev)
