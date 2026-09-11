# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""L14-01: the regulation-tie atom is read in ONE place, and the runline's
reading of it is named, measured and disclosed rather than silent.

THE DEFECT. `game_probabilities` split the margin distribution's d == 0 atom by
the measured extra-innings home rate for the MONEYLINE and, fourteen lines
later, gave the whole of the same atom to BOTH +1.5 sides for the RUNLINE. That
is the unstated claim that no game which goes to extra innings is ever won by
two or more. The completed-game cache the context is fitted on says otherwise
(193 extra-inning games on 2026-09-11: home won 93, by 2+ in 10; away won 100,
by 2+ in 51). Nothing asserted the two markets agreed, so nothing caught it.
On the 2026-09-10 board all six served runline rows carried it and the published
headline, CHW +1.5 at edge 0.08747, sat at 0.05161 under the measured split,
under the 0.06 floor.

WHAT THESE TESTS HOLD
  1. `split_tie_atom` with no split IS the pre-2026-09-11 arithmetic, bit for
     bit, and with the flag off `game_probabilities` routes through it without
     moving a number, so the flag is a one-line rollback.
  2. Under any split the runline stays coherent with the moneyline (a side can
     never be likelier to win by two than to win) and the pair still sums to 1.
  3. The serve flag is ON (owner decision 4, 2026-09-11) with MODEL_VERSION
     bumped; with it off a stray context key cannot switch it on; a lab that
     brings its own fit-window tie never reads a season-wide split, and the labs
     that grade the runline price it on their FIT window's own split.
  4. The measurement counts what it says it counts.
  5. The atom has exactly one reader in the betting and DFS code.
  6. Every runline board row carries the disclosure, priced by the same
     function, and a runline slot's sentence carries no typed number.
  7. The pick card renders the sentence.

Offline: synthetic teams, a tmp context file and the served artifacts read-only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import betting_export as be
import betting_model as bm
import dfs_export as dx

ROOT = Path(__file__).resolve().parent

TEAMS = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
         "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60},
         "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60}}
KW = dict(teams=TEAMS, parks={"KCR": 1.0}, coeffs=dict(bm.LITERATURE_COEFFS),
          home_adj=0.2, diff_shrink=0.8)
MEASURED = {"n_games": 2200, "n_extra_inning_games": 193,
            "n_home_wins": 93, "n_home_wins_by_2plus": 10,
            "n_away_wins": 100, "n_away_wins_by_2plus": 51,
            "home_by_2plus_given_home_win": 0.1075,
            "away_by_2plus_given_away_win": 0.51}
SPLIT = (0.1075, 0.51)
LAMBDAS = ((4.4841, 4.4841), (5.44, 3.89), (3.42, 3.602), (9.5, 1.5), (1.5, 9.5))


def _shipped(dist: dict, th: float) -> dict:
    """The pre-2026-09-11 expressions, copied verbatim from game_probabilities."""
    p_tie = dist.get(0, 0.0)
    p_home_reg = sum(p for d, p in dist.items() if d > 0)
    return {"p_home": p_home_reg + p_tie * th,
            "p_home_minus_1_5": sum(p for d, p in dist.items() if d >= 2),
            "p_away_minus_1_5": sum(p for d, p in dist.items() if d <= -2)}


def _ctx_file(tmp_path: Path, **extra) -> Path:
    p = tmp_path / "betting_model_context.json"
    body = {"extra_inning_home_rate_shrunk": 0.4881,
            "extra_inning_runline_split_fitted": MEASURED}
    body.update(extra)
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. bit for bit while unserved
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lh,la", LAMBDAS)
@pytest.mark.parametrize("r", [None, 1.0 / 0.28086])
def test_no_split_is_the_shipped_arithmetic_bit_for_bit(lh, la, r):
    dist = bm._score_joint(lh, la, r)[0]
    for th in (0.4881, 0.5, 0.0, 1.0):
        want = _shipped(dist, th)
        for split in (None, (0.0, 0.0)):
            got = bm.split_tie_atom(dist, th, split)
            for k, v in want.items():
                assert got[k] == v, (k, th, split)          # ==, not approx
            assert got["p_tie"] == dist.get(0, 0.0)


def test_game_probabilities_prices_exactly_what_shipped_while_unserved(monkeypatch):
    """With the flag off, the served board path (no tie_home, no split) and the
    lab path (an explicit tie_home) both reproduce the whole-atom construction
    exactly: the rollback is bit for bit."""
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", False)
    for th in (None, 0.47):
        gp = bm.game_probabilities("KCR", "CHC", tie_home=th, **KW)
        assert gp is not None
        c = gp["components"]
        dist = bm.margin_distribution(c["lam_home"], c["lam_away"])
        use_th = th if th is not None else bm.league_context()["extra_inning_home_rate"]
        want = _shipped(dist, use_th)
        assert gp["p_home"] == round(want["p_home"], 5)
        assert gp["p_home_minus_1_5"] == round(want["p_home_minus_1_5"], 5)
        assert gp["p_away_minus_1_5"] == round(want["p_away_minus_1_5"], 5)
        assert gp["p_home_plus_1_5"] == round(1.0 - want["p_away_minus_1_5"], 5)
        assert gp["p_away_plus_1_5"] == round(1.0 - want["p_home_minus_1_5"], 5)
        assert gp["runline_tie_split"] is None
        assert gp["p_tie"] == round(dist[0], 5)


# ---------------------------------------------------------------------------
# 2. coherence under any split
# ---------------------------------------------------------------------------
def test_the_split_moves_the_runline_by_the_named_share_and_nothing_else():
    base = bm.game_probabilities("KCR", "CHC", tie_home=0.4881, **KW)
    moved = bm.game_probabilities("KCR", "CHC", tie_home=0.4881,
                                  runline_tie_split=SPLIT, **KW)
    assert moved["p_home"] == base["p_home"], "the moneyline must not move"
    assert moved["fair_total"] == base["fair_total"]
    c = base["components"]
    p_tie = bm.margin_distribution(c["lam_home"], c["lam_away"])[0]
    assert moved["p_home_minus_1_5"] - base["p_home_minus_1_5"] == pytest.approx(
        p_tie * 0.4881 * SPLIT[0], abs=1.5e-5)
    assert moved["p_away_minus_1_5"] - base["p_away_minus_1_5"] == pytest.approx(
        p_tie * (1.0 - 0.4881) * SPLIT[1], abs=1.5e-5)
    # The +1.5 sides lose exactly what the opposite -1.5 sides gain.
    assert moved["p_home_plus_1_5"] < base["p_home_plus_1_5"]
    assert moved["p_away_plus_1_5"] < base["p_away_plus_1_5"]
    assert moved["runline_tie_split"] == [0.1075, 0.51]
    # And runline_at_split is the same function, off the same distribution.
    assert base["runline_at_split"](SPLIT) == {
        k: moved[k] for k in ("p_home_minus_1_5", "p_away_minus_1_5",
                              "p_home_plus_1_5", "p_away_plus_1_5")}


@pytest.mark.parametrize("lh,la", LAMBDAS)
def test_the_runline_can_never_outrun_the_moneyline(lh, la):
    """Winning by two is never likelier than winning, for ANY tie rate and ANY
    conditional. That is the invariant the unconditional auditor form lacked
    and the construction guarantees."""
    dist = bm.margin_distribution(lh, la)
    grid = (0.0, 0.1075, 0.4881, 0.51, 1.0)
    for th in grid:
        for ch in grid:
            for ca in grid:
                a = bm.split_tie_atom(dist, th, (ch, ca))
                assert a["p_home_minus_1_5"] <= a["p_home"] + 1e-12
                assert a["p_away_minus_1_5"] <= (1.0 - a["p_home"]) + 1e-12
                pr = bm._runline_prices(a)
                assert pr["p_home_minus_1_5"] + pr["p_away_plus_1_5"] == pytest.approx(1.0, abs=1e-5)
                assert pr["p_away_minus_1_5"] + pr["p_home_plus_1_5"] == pytest.approx(1.0, abs=1e-5)
    # At the corner, the whole of each side's share of the tie is a two-run win.
    full = bm.split_tie_atom(dist, 0.5, (1.0, 1.0))
    assert full["p_home_minus_1_5"] + full["p_away_minus_1_5"] == pytest.approx(
        sum(dist.values()) - sum(p for d, p in dist.items() if abs(d) == 1), abs=1e-12)


@pytest.mark.parametrize("bad", [float("nan"), -0.01, 1.01])
def test_a_non_probability_is_refused_not_priced(bad):
    dist = bm.margin_distribution(4.5, 4.5)
    with pytest.raises(ValueError):
        bm.split_tie_atom(dist, bad)
    with pytest.raises(ValueError):
        bm.split_tie_atom(dist, 0.5, (bad, 0.5))
    with pytest.raises(ValueError):
        bm.split_tie_atom(dist, 0.5, (0.1, bad))


# ---------------------------------------------------------------------------
# 3. the serve flag, the stray key and the lab rule
# ---------------------------------------------------------------------------
def test_tripwire_the_split_is_served():
    """SERVE_RUNLINE_TIE_SPLIT went live on 2026-09-11 (owner decision 4, ahead
    of the runline margin gate, which still decides its successor) in ONE commit
    with the MODEL_VERSION bump and the lab wiring. THE SERVED STATE, and it
    fails rather than skips: the price reads the served context's measured split
    whether or not a v2 `--context` has rewritten the served key yet, and once
    it has, the served key IS the measurement."""
    assert bm.SERVE_RUNLINE_TIE_SPLIT is True, (
        "the runline tie split was switched off; read the flag's comment")
    assert bm.MODEL_VERSION != "betting_runs_v1", (
        "serving the split without a MODEL_VERSION bump pools two pricers "
        "in every ledger")
    ctx = json.loads((ROOT / "data" / "betting_model_context.json").read_text(encoding="utf-8"))
    fitted = ctx.get("extra_inning_runline_split_fitted")
    pair = bm._runline_split_pair(fitted)
    assert pair is not None, "the served context carries no runline split measurement"
    assert bm.served_runline_tie_split() == pair
    if ctx.get("model_version") == bm.MODEL_VERSION:
        assert ctx.get("extra_inning_runline_split") == fitted, (
            "a v2 context whose served split key does not carry the measurement")


def test_a_context_written_before_the_flip_still_prices_the_split(tmp_path, monkeypatch):
    """A context from before the flip carries the measurement beside a null
    served key. With the flag on the price reads the measurement, so a refit
    that has not yet run cannot leave the runline on the whole atom."""
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(
        tmp_path, extra_inning_runline_split=None, model_version="betting_runs_v1"))
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", True)
    assert bm.served_runline_tie_split() == SPLIT
    assert bm.game_probabilities("KCR", "CHC", **KW)["runline_tie_split"] == [0.1075, 0.51]
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", False)
    assert bm.served_runline_tie_split() is None


def test_rows_carry_the_context_version_beside_the_pricer(tmp_path, monkeypatch):
    """The ledger key comes from the code; the coefficients come from the
    context. A night whose context was fitted under another version stamps
    both, so the ledger can keep them apart, and the build says so."""
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(tmp_path, model_version=bm.MODEL_VERSION))
    assert bm.context_model_version() == bm.MODEL_VERSION
    assert be.context_version_note(bm.MODEL_VERSION) is None
    assert be.context_version_note(None) is None
    slot = {"game_pk": 9, "market": "runline", "side": "home", "point": 1.5,
            "label": "KCR +1.5", "odds": -190, "model_prob": 0.7, "edge": 0.08,
            "min_edge_used": 0.06}
    row = be.record_row(slot, slate_date="2026-09-11", evald={})
    assert row["model_version"] == bm.MODEL_VERSION
    assert row["context_version"] == bm.MODEL_VERSION
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(tmp_path, model_version="betting_runs_v1"))
    row = be.record_row(slot, slate_date="2026-09-11", evald={})
    assert (row["model_version"], row["context_version"]) == (bm.MODEL_VERSION,
                                                              "betting_runs_v1")
    note = be.context_version_note("betting_runs_v1")
    assert "betting_runs_v1" in note and bm.MODEL_VERSION in note


def test_a_stray_served_key_cannot_switch_the_split_on(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", False)
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(
        tmp_path, extra_inning_runline_split=MEASURED))
    assert bm.served_runline_tie_split() is None
    gp = bm.game_probabilities("KCR", "CHC", **KW)
    assert gp["runline_tie_split"] is None
    c = gp["components"]
    want = _shipped(bm.margin_distribution(c["lam_home"], c["lam_away"]), 0.4881)
    assert gp["p_home_minus_1_5"] == round(want["p_home_minus_1_5"], 5)


def test_a_lab_that_brings_its_own_tie_never_reads_the_season_split(tmp_path, monkeypatch):
    """With the flag ON, the SERVING path reads the served split. A caller that
    passes its own fit-window tie_home gets the whole-atom construction unless
    it passes its own split too: a season-wide split in a held-out grade is a
    leak, the rule _fit_tie_home states for the tie rate itself."""
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(
        tmp_path, extra_inning_runline_split=MEASURED))
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", True)
    assert bm.served_runline_tie_split() == SPLIT
    served = bm.game_probabilities("KCR", "CHC", **KW)
    assert served["runline_tie_split"] == [0.1075, 0.51]
    lab = bm.game_probabilities("KCR", "CHC", tie_home=0.4881, **KW)
    assert lab["runline_tie_split"] is None
    assert lab["p_home"] == served["p_home"]
    assert lab["p_home_plus_1_5"] > served["p_home_plus_1_5"]


def test_the_labs_price_the_runline_on_their_fit_window_split(monkeypatch):
    """With the flag on, the two labs that READ a runline probability (the
    section 11a dispersion arms and the backtest's per-market grade) price it on
    the split measured on their FIT window alone; with it off they price the
    whole-atom construction, which is what the board then serves."""
    games = [_g(4, 3, 10), _g(6, 4, 11), _g(2, 3, 10), _g(1, 6, 13), _g(5, 1)]
    assert bm._lab_runline_split(games) == (0.5, 0.5)
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", False)
    assert bm._lab_runline_split(games) is None
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", True)
    # No extra-inning win on one side: not a measurement, whole atom.
    assert bm._lab_runline_split([_g(4, 3, 10)]) is None
    src = (ROOT / "betting_model.py").read_text(encoding="utf-8")
    arm = src[src.index("def _dispersion_arm("):]
    arm = arm[:arm.index("\ndef ")]
    assert "rl_split = _lab_runline_split(fit_games)" in arm
    assert "runline_tie_split=rl_split" in arm
    grade = src[src.index("    def _grade(fit_games, eval_games"):]
    grade = grade[:6000]
    assert "rl_split = _lab_runline_split(fit_games)" in grade
    assert "runline_tie_split=rl_split" in grade


def test_a_served_split_prices_the_runline_and_leaves_nothing_to_disclose(
        tmp_path, monkeypatch):
    """The served state: the context carries the split, every runline row is
    priced on it, the row's disclosure says so with a zero shift, and the slot
    carries no tie-atom sentence."""
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(
        tmp_path, extra_inning_runline_split=MEASURED))
    ev = {"event_id": "e9", "home_team": "Kansas City Royals",
          "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "spreads": {"home": {"price": -190, "point": 1.5},
                                           "away": {"price": 160, "point": -1.5}}}}}
    g = {"game_pk": 9, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    rows = be.team_bets([g], [ev], teams=TEAMS, parks={"KCR": 1.0}, starters={},
                        now=datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc))
    gp = bm.game_probabilities("KCR", "CHC", teams=TEAMS, parks={"KCR": 1.0})
    assert gp["runline_tie_split"] == [0.1075, 0.51]
    keys = be._runline_side_keys(False)
    for r in rows[0]["runline"]:
        assert r["model_prob"] == gp[keys[r["side"]]]
        ta = r["tie_atom"]
        assert ta["split_served"] is True and ta["shift_if_split"] == 0.0
        assert be.tie_atom_caveat({**r, "market": "runline"}, 0.06) is None


def test_a_malformed_fitted_block_is_absent_not_zero(tmp_path, monkeypatch):
    for blk in (None, {}, {"home_by_2plus_given_home_win": 1.4,
                           "away_by_2plus_given_away_win": 0.5},
                {"home_by_2plus_given_home_win": "x",
                 "away_by_2plus_given_away_win": 0.5}):
        monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(
            tmp_path, extra_inning_runline_split_fitted=blk))
        assert bm.fitted_runline_tie_split() is None
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(tmp_path))
    assert bm.fitted_runline_tie_split() == MEASURED


# ---------------------------------------------------------------------------
# 4. the measurement
# ---------------------------------------------------------------------------
def _g(h, a, inn=9):
    return {"home_runs": h, "away_runs": a, "innings": inn}


def test_the_measurement_counts_what_it_says():
    games = [_g(5, 1), _g(0, 7),                                  # regulation: ignored
             _g(4, 3, 10), _g(6, 4, 11), _g(3, 2, 12),            # home wins in extras
             _g(2, 3, 10), _g(2, 5, 10), _g(1, 6, 13), _g(3, 4, 11)]  # away wins
    m = bm._fit_runline_tie_split(games)
    assert m == {"n_games": 9, "n_extra_inning_games": 7,
                 "n_home_wins": 3, "n_home_wins_by_2plus": 1,
                 "n_away_wins": 4, "n_away_wins_by_2plus": 2,
                 "home_by_2plus_given_home_win": round(1 / 3, 4),
                 "away_by_2plus_given_away_win": 0.5}
    # A window with no extra-inning win on one side is not a measurement.
    assert bm._fit_runline_tie_split([_g(4, 3, 10)]) is None
    assert bm._fit_runline_tie_split([_g(4, 3), _g(1, 2)]) is None


# ---------------------------------------------------------------------------
# 5. one reader
# ---------------------------------------------------------------------------
def test_the_tie_atom_has_exactly_one_reader():
    src = (ROOT / "betting_model.py").read_text(encoding="utf-8")
    assert src.count("dist.get(0") == 1
    body = src[src.index("def split_tie_atom("):src.index("def _runline_prices(")]
    assert "dist.get(0" in body, "the one read must live inside split_tie_atom"
    for name in ("betting_export.py", "dfs_export.py"):
        assert "dist.get(0" not in (ROOT / name).read_text(encoding="utf-8"), name


def test_dfs_implied_totals_read_the_same_function(monkeypatch):
    calls = []
    real = bm.split_tie_atom

    def spy(dist, tie_home, runline_split=None):
        calls.append(tie_home)
        return real(dist, tie_home, runline_split)

    monkeypatch.setattr(bm, "split_tie_atom", spy)
    home, away, edged = dx._split_total(9.0, 0.60, 0.4875)
    assert calls and set(calls) == {0.4875}
    assert home + away == pytest.approx(9.0) and home > away and not edged


# ---------------------------------------------------------------------------
# 6. the disclosure on the board and on the slot
# ---------------------------------------------------------------------------
def _board(tmp_path, monkeypatch, *, home_point=1.5):
    """The UNSERVED board: the disclosure these tests hold describes a split the
    price does not carry, which since v2 is the rollback state (flag off). The
    served state has its own test above."""
    monkeypatch.setattr(bm, "SERVE_RUNLINE_TIE_SPLIT", False)
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx_file(tmp_path))
    ev = {"event_id": "e9", "home_team": "Kansas City Royals",
          "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "spreads": {"home": {"price": -190, "point": home_point},
                                           "away": {"price": 160, "point": -home_point}}}}}
    g = {"game_pk": 9, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    return be.team_bets([g], [ev], teams=TEAMS, parks={"KCR": 1.0}, starters={},
                        now=datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc))


@pytest.mark.parametrize("home_point", [1.5, -1.5])
def test_every_runline_row_carries_the_tie_atom_priced_by_the_one_function(
        tmp_path, monkeypatch, home_point):
    rows = _board(tmp_path, monkeypatch, home_point=home_point)
    rl = rows[0]["runline"]
    assert len(rl) == 2
    gp = bm.game_probabilities("KCR", "CHC", teams=TEAMS, parks={"KCR": 1.0})
    cf = gp["runline_at_split"](SPLIT)
    keys = be._runline_side_keys(home_point < 0)
    for r in rl:
        ta = r["tie_atom"]
        assert r["model_prob"] == gp[keys[r["side"]]], "the served price did not move"
        assert ta["split_served"] is False
        assert ta["p_tie"] == gp["p_tie"]
        assert ta["model_prob_if_split"] == cf[keys[r["side"]]]
        assert ta["shift_if_split"] == round(ta["model_prob_if_split"] - r["model_prob"], 5)
        assert ta["edge_if_split"] == pytest.approx(
            ta["model_prob_if_split"] - r["market_fair_prob"], abs=1e-5)
        for k in ("n_extra_inning_games", "n_home_wins", "n_home_wins_by_2plus",
                  "n_away_wins", "n_away_wins_by_2plus", "n_games"):
            assert ta[k] == MEASURED[k]
    by_point = {r["point"]: r["tie_atom"]["shift_if_split"] for r in rl}
    assert by_point[1.5] < 0 < by_point[-1.5], "a +1.5 side runs high, a -1.5 side low"
    assert by_point[1.5] == pytest.approx(-by_point[-1.5], abs=1e-5)


def test_no_measurement_means_no_stamp_not_a_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "CONTEXT_PATH", tmp_path / "missing.json")
    ev = {"event_id": "e9", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "spreads": {"home": {"price": -190, "point": 1.5},
                                           "away": {"price": 160, "point": -1.5}}}}}
    g = {"game_pk": 9, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    rows = be.team_bets([g], [ev], teams=TEAMS, parks={"KCR": 1.0}, starters={},
                        now=datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc))
    assert all("tie_atom" not in r for r in rows[0]["runline"])


def _pcts(s: str) -> list[str]:
    return re.findall(r"[+-]?\d+\.\d%", s)


def test_the_slot_sentence_is_interpolated_from_the_row(tmp_path, monkeypatch):
    rows = _board(tmp_path, monkeypatch)
    plus = next(r for r in rows[0]["runline"] if r["point"] == 1.5)
    ta = plus["tie_atom"]
    for thr in (0.0, 0.5):
        s = be.tie_atom_caveat({**plus, "market": "runline"}, thr)
        want = [f"{100 * ta['p_tie']:.1f}%", f"{100 * ta['model_prob_if_split']:.1f}%",
                f"{100 * plus['model_prob']:.1f}%", f"{100 * ta['edge_if_split']:+.1f}%",
                f"{100 * thr:.1f}%",
                f"{100 * ta['n_extra_inning_games'] / ta['n_games']:.1f}%"]
        assert _pcts(s) == want, "every percentage must be a row field, in order"
        for k in ("n_extra_inning_games", "n_home_wins", "n_home_wins_by_2plus",
                  "n_away_wins", "n_away_wins_by_2plus", "n_games"):
            assert str(ta[k]) in s, k
        assert ("would not clear" in s) is (ta["edge_if_split"] < thr)
        assert "\u2014" not in s and "\u2013" not in s
    slot = be._publish_slot({**plus, "market": "runline"}, "pick_of_the_day",
                            thr=0.06, prov=True)
    assert slot["tie_atom_caveat"] == be.tie_atom_caveat({**plus, "market": "runline"}, 0.06)
    assert slot["caveat"] == be.POISSON_CAVEAT, "the dispersion caveat still rides"
    # A total never carries it, and a served split has nothing left to disclose.
    assert "tie_atom_caveat" not in be._publish_slot(
        {"market": "total", "model_prob": 0.6, "edge": 0.1}, "pick_of_the_day",
        thr=0.06, prov=True)
    served = {**plus, "tie_atom": {**ta, "split_served": True}}
    assert be.tie_atom_caveat(served, 0.06) is None


def test_the_served_artifact_carries_a_true_disclosure_when_it_carries_one():
    """Against data/betting.json as built. Skips on an artifact built before the
    measurement reached the context; once it has, every runline row must carry
    the block and every block must add up."""
    payload = json.loads((ROOT / "data" / "betting.json").read_text(encoding="utf-8"))
    rl = [r for b in payload.get("team_bets") or [] for r in (b.get("runline") or [])]
    stamped = [r for r in rl if r.get("tie_atom")]
    if not stamped:
        pytest.skip("artifact predates the tie-atom measurement; rebuild the context "
                    "and the payload")
    assert len(stamped) == len([r for r in rl if r.get("model_prob") is not None])
    for r in stamped:
        ta = r["tie_atom"]
        assert ta["shift_if_split"] == pytest.approx(
            ta["model_prob_if_split"] - r["model_prob"], abs=1e-5)
        if (ta["split_served"] is False and ta["n_home_wins_by_2plus"]
                and ta["n_away_wins_by_2plus"] and r.get("point") in (1.5, -1.5)):
            assert (ta["shift_if_split"] < 0) is (r["point"] == 1.5)
    for key in ("pick_of_the_day", "longshot_of_the_day"):
        p = payload.get(key)
        if p and p.get("market") == "runline" and p.get("tie_atom"):
            assert p.get("tie_atom_caveat") == be.tie_atom_caveat(p, p.get("min_edge_used"))


# ---------------------------------------------------------------------------
# 7. the pick card
# ---------------------------------------------------------------------------
def test_the_pick_card_renders_the_tie_atom_sentence():
    tb = pytest.importorskip("test_betting")
    sentinel = "Extra innings: TIE-ATOM-SENTINEL 68.1% rather than 71.7%"
    old = '"caveat": "this is a runline or total, and the margin model is a Poisson difference"}'
    assert old in tb.LIVE_PAYLOAD
    payload = tb.LIVE_PAYLOAD.replace(
        old, old[:-1] + ', "tie_atom_caveat": ' + json.dumps(sentinel) + "}")
    c = tb._ctx(tb._fetch_js(main=payload, learning=tb.LEARNING_ARTIFACT,
                             evald=tb.EVAL_ARTIFACT, clv=tb.CLV_EMPTY))
    text = tb._visible_text(c.eval("__show('potd')"))
    assert sentinel in text
    plain = tb._ctx(tb._fetch_js(main=tb.LIVE_PAYLOAD, learning=tb.LEARNING_ARTIFACT,
                                 evald=tb.EVAL_ARTIFACT, clv=tb.CLV_EMPTY))
    assert "TIE-ATOM-SENTINEL" not in tb._visible_text(plain.eval("__show('potd')"))
