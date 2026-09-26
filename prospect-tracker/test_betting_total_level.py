# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""BET1: why most value totals are Overs, the flag that recentres the total, and
the invariant that would have caught the skew.

THE DEFECT. On every cached slate the model's positive-edge totals leaned Over
(323 to 102 re-priced across 26 slates; 13 of 15 on the served 2026-09-11
board). The model's MEAN total is right on the honest fit half (+0.058 runs);
the lean is the Poisson centre: a Poisson puts its middle at the mean, real run
totals split about a run lower, and a book posts its line where they split.

WHAT THESE TESTS HOLD
  1. SERVE_TOTAL_LEVEL is False and a stray context key cannot switch it on.
  2. With no recentre the total is the shipped Poisson, bit for bit.
  3. Under ANY recentre the moneyline and the runline are byte-identical, at the
     model and at the export, and only the total moves, in the named direction.
  4. The serving path reads the served constant; a lab bringing its own
     tie_home does not.
  5. The fit recovers a known shift when the truth IS Poisson, and reproduces
     the finding when the truth is overdispersed: mean arm near zero, centre arm
     negative, Over 8.5 overstated by the incumbent.
  6. The slate lean check fires on a one-sided slate, stays quiet on a balanced
     or small one, stamps every total row only when it fires, and its sentence
     carries no dash the copy rule forbids.
  7. The page renders the sentence on the slot, the badge and the board head.

Offline: synthetic teams, synthetic rows, a tmp context file.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import betting_export as be
import betting_model as bm

ROOT = Path(__file__).resolve().parent

TEAMS = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
         "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60},
         "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60}}
KW = dict(teams=TEAMS, parks={"KCR": 1.0}, coeffs=dict(bm.LITERATURE_COEFFS),
          home_adj=0.2, diff_shrink=0.8)
ML_RL_KEYS = ("p_home", "p_away", "p_home_minus_1_5", "p_away_minus_1_5",
              "p_home_plus_1_5", "p_away_plus_1_5", "p_tie", "lam_home", "lam_away",
              "fair_total")


def _ctx(tmp_path: Path, **extra) -> Path:
    p = tmp_path / "betting_model_context.json"
    p.write_text(json.dumps(extra), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. the flag
# ---------------------------------------------------------------------------
def test_the_total_level_is_not_served():
    """TRIPWIRE. The pre-registered gate returned FAIL on 2026-09-11 (the centre
    arm at t -0.005, -0.714, -0.797, -1.309 across the four splits). Flip this
    only with the gate, section 7f and MODEL_VERSION in the same commit."""
    assert bm.SERVE_TOTAL_LEVEL is False


def test_a_stray_context_key_cannot_recentre_a_total(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_level=-0.5))
    assert bm.served_total_level() is None
    gp = bm.game_probabilities("KCR", "CHC", **KW)
    assert gp["total_level_runs"] is None and gp["total_price_mean"] is None


def test_the_served_reader_rejects_a_constant_outside_the_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "SERVE_TOTAL_LEVEL", True)
    for bad in (float("nan"), 99.0, "x", None):
        monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_level=bad))
        assert bm.served_total_level() is None
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_level=-0.25))
    assert bm.served_total_level() == -0.25


# ---------------------------------------------------------------------------
# 2 and 3. bit for bit off, and the moneyline and runline never move
# ---------------------------------------------------------------------------
def test_no_recentre_is_the_shipped_poisson_total_bit_for_bit():
    for tl in (None, 0.0):
        gp = bm.game_probabilities("KCR", "CHC", tie_home=0.49, total_level=tl, **KW)
        c = gp["components"]
        lam = c["lam_home"] + c["lam_away"]
        want = bm._poisson_pmf(lam, 40)
        for line in (7.5, 8.5, 9.0, 10.5):
            got = gp["total_sides"](line)
            ref = bm.total_side_probabilities(want, line)
            assert got == ref                                        # ==, not approx
        assert gp["total_level_runs"] is None


@pytest.mark.parametrize("tl", [-1.0, -0.2315, 0.3])
@pytest.mark.parametrize("alpha", [0.0, 0.28425])
def test_a_recentre_moves_the_total_and_nothing_else(tl, alpha):
    base = bm.game_probabilities("KCR", "CHC", tie_home=0.49, total_level=0.0,
                                 run_alpha=alpha, **KW)
    moved = bm.game_probabilities("KCR", "CHC", tie_home=0.49, total_level=tl,
                                  run_alpha=alpha, **KW)
    for k in ML_RL_KEYS:
        assert moved[k] == base[k], k                               # byte-identical
    assert moved["runline_at_split"]((0.1075, 0.51)) == base["runline_at_split"]((0.1075, 0.51))
    assert moved["total_level_runs"] == round(tl, 4)
    assert moved["total_price_mean"] == pytest.approx(base["fair_total"] + tl, abs=0.011)
    for line in (7.5, 8.5, 9.5):
        o0 = base["total_sides"](line)["p_over"]
        o1 = moved["total_sides"](line)["p_over"]
        assert (o1 < o0) if tl < 0 else (o1 > o0), (line, tl)


def test_the_export_moneyline_and_runline_rows_are_identical_under_the_flag(tmp_path,
                                                                           monkeypatch):
    """The proof at the surface the page reads: flip the flag with a served
    constant and every moneyline and runline row, and every moneyline field on
    the model row, is the same JSON."""
    ev = {"event_id": "e1", "home_team": "Kansas City Royals",
          "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "h2h": {"home": -120, "away": 110},
                               "spreads": {"home": {"price": 150, "point": -1.5},
                                           "away": {"price": -170, "point": 1.5}},
                               "totals": {"over": {"price": -110, "point": 8.5},
                                          "under": {"price": -110, "point": 8.5}}}}}
    g = {"game_pk": 3, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    now = datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc)
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_level=-0.25))

    def board():
        return be.team_bets([g], [ev], teams=TEAMS, parks={"KCR": 1.0}, starters={},
                            now=now)[0]

    monkeypatch.setattr(bm, "SERVE_TOTAL_LEVEL", False)
    off = board()
    monkeypatch.setattr(bm, "SERVE_TOTAL_LEVEL", True)
    on = board()
    for k in ("moneyline", "runline"):
        assert json.dumps(on[k], sort_keys=True) == json.dumps(off[k], sort_keys=True), k
    for k in ("p_home", "p_away", "lam_home", "lam_away", "fair_total"):
        assert on["model"][k] == off["model"][k], k
    assert "total_level_runs" not in off["model"], "a flag-off board gained a key"
    assert on["model"]["total_level_runs"] == -0.25
    o_off = [s for s in off["total"]["sides"] if s["side"] == "over"][0]
    o_on = [s for s in on["total"]["sides"] if s["side"] == "over"][0]
    assert o_on["model_prob"] < o_off["model_prob"]
    assert o_on["market_fair_prob"] == o_off["market_fair_prob"], (
        "the market side of the edge must not move: the recentre prices the model only")


# ---------------------------------------------------------------------------
# 4. which callers read the served constant
# ---------------------------------------------------------------------------
def test_the_serving_path_reads_it_and_a_lab_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "SERVE_TOTAL_LEVEL", True)
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_level=-0.4))
    served = bm.game_probabilities("KCR", "CHC", **KW)
    lab = bm.game_probabilities("KCR", "CHC", tie_home=0.49, **KW)
    assert served["total_level_runs"] == -0.4
    assert lab["total_level_runs"] is None, "a lab never reads a season-wide constant"


# ---------------------------------------------------------------------------
# 5. the fit
# ---------------------------------------------------------------------------
def _population(pmf, n_total, model_mean):
    rows = []
    for k, p in enumerate(pmf):
        rows.extend([(model_mean, k)] * int(round(p * n_total)))
    return rows


def test_the_fit_recovers_a_known_shift_when_the_truth_is_poisson():
    rows = _population(bm._poisson_pmf(8.3, 40), 2000, 8.8)
    fit = bm.fit_total_level(rows)
    assert fit["mean"] == pytest.approx(-0.5, abs=0.03)
    assert fit["centre"] == pytest.approx(-0.5, abs=0.05)
    assert fit["log_loss_centre"] <= fit["log_loss_incumbent"]


def test_the_fit_reproduces_the_finding_when_the_truth_is_overdispersed():
    """The mechanism, synthetically: a model whose MEAN is exactly right and whose
    shape is Poisson, against totals with var/mean 2.35 (the fit half's). The
    mean arm finds nothing to fix, the incumbent overprices Over 8.5, and the
    centre arm moves down."""
    mu = 8.8
    r = mu / 1.35                                    # var = mu + mu^2 / r = 2.35 mu
    rows = _population(bm._nb2_pmf(mu, r, 60), 2000, mu)
    fit = bm.fit_total_level(rows)
    assert abs(fit["mean"]) < 0.05
    assert fit["centre"] < -0.1
    p85 = next(x for x in fit["per_line"] if x["line"] == 8.5)
    assert p85["model_over_incumbent"] > p85["observed_over"] + 0.03
    assert fit["median_actual_total"] < fit["mean_actual_total"]


def test_the_fit_is_deterministic_and_refuses_an_empty_window():
    rows = _population(bm._poisson_pmf(9.0, 40), 500, 9.2)
    assert bm.fit_total_level(rows) == bm.fit_total_level(rows)
    assert bm.fit_total_level([]) is None
    assert bm.fit_total_level([(9.0, 8)]) is None


def test_the_gate_criteria_name_the_fixed_grid_and_the_byte_identity():
    txt = bm.TOTAL_LEVEL_GATE_CRITERIA
    assert "(7.5, 8.5, 9.5, 10.5)" in txt and "t >= 1.645" in txt
    assert "byte-identical" in txt and "ALL FOUR" in txt
    assert tuple(bm.TOTAL_LEVEL_LINES) == (7.5, 8.5, 9.5, 10.5)


# ---------------------------------------------------------------------------
# 6. the slate lean check
# ---------------------------------------------------------------------------
def _bet(pk, lean, line=8.5, fair_total=9.2):
    p_mkt = 0.5
    over = {"side": "over", "model_prob": p_mkt + lean, "market_fair_prob": p_mkt,
            "edge": lean, "odds": -110, "book": "b"}
    under = {"side": "under", "model_prob": 1 - p_mkt - lean, "market_fair_prob": 1 - p_mkt,
             "edge": -lean, "odds": -110, "book": "b"}
    return {"game_pk": pk, "start": None, "home": {"org": "KCR"}, "away": {"org": "CHC"},
            "model": {"fair_total": fair_total},
            "total": {"line": line, "sides": [over, under], "p_push": 0.0}}


def test_the_check_fires_on_a_one_sided_slate_and_stamps_every_total_row():
    bets = [_bet(i, 0.06 + 0.01 * (i % 3)) for i in range(12)]
    chk = be.total_level_check(bets)
    assert chk["fires"] and chk["direction"] == "over"
    assert chk["n"] == 12 and chk["n_positive_edge"] == {"over": 12, "under": 0}
    assert chk["mean_gap_runs"] == pytest.approx(0.7, abs=1e-9)
    assert be.stamp_total_level_caveat(bets, chk) == 24
    assert all(s["total_level_caveat"] == chk["caveat"]
               for b in bets for s in b["total"]["sides"])
    # Since the owner's 2026-09-25 bar a caveated total fills no slot, and the
    # seam counts what it took out.
    stats: dict = {}
    cands = be._floor_clearing_sides(bets, 0.06, ledger_closed=frozenset(), stats=stats)
    assert not cands and stats["n_total_lean_barred_sides"] == 12


def test_with_the_bar_off_a_slot_is_a_board_row_verbatim_and_inherits_the_sentence(
        monkeypatch):
    monkeypatch.setattr(be, "BAR_TOTAL_LEAN_SLOTS", False)
    bets = [_bet(i, 0.06 + 0.01 * (i % 3)) for i in range(12)]
    be.stamp_total_level_caveat(bets, be.total_level_check(bets))
    cands = be._floor_clearing_sides(bets, 0.06, ledger_closed=frozenset())
    assert cands and all(c.get("total_level_caveat") for c in cands)


def _mixed_slate(total_edge=0.40, ml_edge=0.20):
    """Twelve leaning totals (so the check fires) plus one game whose moneyline
    also clears the floor, at a smaller edge and a lower model probability than
    the top Over, so the Over would win the headline slot if it could."""
    bets = [_bet(i, 0.06 + 0.01 * (i % 3)) for i in range(12)]
    bets[0]["total"]["sides"][0].update({"edge": total_edge, "model_prob": 0.90})
    bets.append({"game_pk": 99, "start": None, "home": {"org": "BBB"},
                 "away": {"org": "AAA"},
                 "moneyline": [{"side": "home", "edge": ml_edge, "odds": -110,
                                "book": "b", "model_prob": 0.60,
                                "market_fair_prob": 0.60 - ml_edge,
                                "kelly_full": 0.2}]})
    return bets


def test_a_caveated_total_never_fills_the_headline_slot(monkeypatch):
    """THE DEFECT THIS PINS (owner decision 2026-09-25): the public record's
    first row was a caveated Over on a leaning slate. With the bar on, the
    moneyline takes the slot, the census still counts the barred totals as
    having cleared the floor, and the payload names the bar.

    MUTATION: drop the BAR_TOTAL_LEAN_SLOTS test at the seam and the Over
    (model 0.90) wins the slot again."""
    monkeypatch.setattr(be, "ledger_closed_markets", lambda *a, **k: frozenset())
    bets = _mixed_slate()
    chk = be.total_level_check(bets)
    assert chk["fires"] and chk["slot_bar"] is True
    be.stamp_total_level_caveat(bets, chk)
    slots, _, meta = be.provisional_picks(bets, odds_priceable=True, evald={})
    potd = slots["pick_of_the_day"]
    assert potd is not None and potd["market"] == "moneyline"
    assert meta["total_lean_bar"] is True
    assert meta["n_total_lean_barred_sides"] == 12
    assert meta["n_floor_clearing_sides"] == 1
    assert meta["n_floor_clearing_sides_before_policy"] == 13


def test_when_only_caveated_totals_clear_the_slot_is_empty_and_says_why(monkeypatch):
    monkeypatch.setattr(be, "ledger_closed_markets", lambda *a, **k: frozenset())
    bets = [_bet(i, 0.06 + 0.01 * (i % 3)) for i in range(12)]
    be.stamp_total_level_caveat(bets, be.total_level_check(bets))
    slots, reason, meta = be.provisional_picks(bets, odds_priceable=True, evald={})
    assert slots["pick_of_the_day"] is None and slots["longshot_of_the_day"] is None
    assert "12 total side(s) also cleared it and fill no slot" in reason
    assert "owner decision 2026-09-25" in reason


def test_a_slate_that_does_not_lean_keeps_its_totals_eligible(monkeypatch):
    """The bar reads the stamped caveat, so a balanced slate's totals compete
    exactly as before."""
    monkeypatch.setattr(be, "ledger_closed_markets", lambda *a, **k: frozenset())
    bets = [_bet(i, (0.07 if i % 2 else -0.07)) for i in range(12)]
    chk = be.total_level_check(bets)
    assert not chk["fires"]
    assert be.stamp_total_level_caveat(bets, chk) == 0
    stats: dict = {}
    cands = be._floor_clearing_sides(bets, 0.06, ledger_closed=frozenset(), stats=stats)
    assert cands and all(c["market"] == "total" for c in cands)
    assert stats["n_total_lean_barred_sides"] == 0


# The served 2026-09-11 board, the incident the owner saw: (line, fair_total,
# Over model_prob, Over market_fair_prob) for its 15 priced totals, copied off
# data/betting.json generated 2026-09-11T17:35:09Z.
BOARD_2026_09_11 = [
    (8.5, 9.67, 0.62905, 0.48765), (8.0, 9.56, 0.70102, 0.5), (7.5, 8.76, 0.64683, 0.51235),
    (8.0, 8.81, 0.59894, 0.50452), (8.0, 9.18, 0.65199, 0.4854), (8.5, 9.02, 0.54732, 0.4809),
    (7.5, 7.6, 0.49041, 0.5279), (7.5, 9.36, 0.71623, 0.48765), (7.0, 7.25, 0.51532, 0.5146),
    (8.0, 9.23, 0.65867, 0.49781), (7.5, 8.31, 0.58905, 0.51235), (8.0, 9.37, 0.67678, 0.51235),
    (10.0, 9.86, 0.45648, 0.51235), (8.5, 9.35, 0.58995, 0.51235), (8.0, 8.57, 0.56301, 0.4854),
]


def test_the_check_fires_on_the_board_the_owner_saw():
    """The replay: this is the law that would have caught it."""
    bets = []
    for i, (line, ft, pm, pf) in enumerate(BOARD_2026_09_11):
        b = _bet(i, pm - pf, line=line, fair_total=ft)
        b["total"]["sides"][0].update(model_prob=pm, market_fair_prob=pf, edge=pm - pf)
        b["total"]["sides"][1].update(model_prob=1 - pm, market_fair_prob=1 - pf,
                                      edge=pf - pm)
        bets.append(b)
    chk = be.total_level_check(bets)
    assert chk["fires"] and chk["direction"] == "over"
    assert chk["n"] == 15 and chk["n_positive_edge"] == {"over": 13, "under": 2}
    assert chk["mean_lean"] == pytest.approx(0.09983, abs=1e-5)
    assert chk["t"] == pytest.approx(4.791, abs=1e-3)
    assert chk["mean_gap_runs"] == pytest.approx(0.893, abs=1e-3)


def test_a_carried_board_carries_a_check_of_its_own_rows(monkeypatch):
    """An empty build keeps yesterday's rows; the lean check must describe
    those rows, not tonight's empty slate."""
    prev = {"team_bets": [_bet(i, 0.07 + 0.01 * (i % 2)) for i in range(10)],
            "slate_date": "2026-09-10", "generated_at": "2026-09-10T17:00:00+00:00",
            "status": {}}
    monkeypatch.setattr(be, "_load", lambda name: prev)
    monkeypatch.setattr(be, "_record_board_anomaly", lambda *a, **k: None)
    payload = {"team_bets": [], "status": {}, "pick_blockers": [], "pick_reason": "",
               "props_fair_lines": {}, "slate_date": "2026-09-11",
               "total_level_check": be.total_level_check([])}
    out = be._carry_previous_board(payload, "no games priced")
    assert out["total_level_check"]["fires"] and out["total_level_check"]["n"] == 10
    assert all(s.get("total_level_caveat") for b in out["team_bets"]
               for s in b["total"]["sides"])


def test_a_slate_of_identical_leans_fires_without_a_t():
    """A constant lean has no spread and so no t. An exact lean past the band is
    the strongest case, so it fires rather than hiding behind a zero division;
    a constant lean inside the band still does not."""
    chk = be.total_level_check([_bet(i, 0.09) for i in range(10)])
    assert chk["t"] is None and chk["fires"]
    assert not be.total_level_check([_bet(i, 0.02) for i in range(10)])["fires"]


def test_the_check_is_quiet_on_a_balanced_or_small_slate():
    balanced = [_bet(i, 0.08 if i % 2 else -0.08) for i in range(12)]
    chk = be.total_level_check(balanced)
    assert not chk["fires"] and chk["caveat"] is None
    assert be.stamp_total_level_caveat(balanced, chk) == 0
    assert not any("total_level_caveat" in s for b in balanced for s in b["total"]["sides"])
    small = [_bet(i, 0.10) for i in range(be.TOTAL_LEAN_MIN_GAMES - 1)]
    assert not be.total_level_check(small)["fires"]
    inside = [_bet(i, 0.02 + 0.001 * i) for i in range(12)]
    assert not be.total_level_check(inside)["fires"], "inside the 0.03 band"
    assert be.total_level_check([])["n"] == 0


def test_the_check_names_an_under_lean_too():
    chk = be.total_level_check([_bet(i, -0.07 - 0.01 * (i % 2)) for i in range(10)])
    assert chk["fires"] and chk["direction"] == "under"
    assert chk["caveat"].startswith("Slate leans Under")


def test_the_sentence_is_built_from_the_blocks_and_obeys_the_copy_rule():
    fitted = {"n": 305, "mean_model_total": 8.8649, "mean_actual_total": 8.8066,
              "per_line": [{"line": 8.5, "model_over_incumbent": 0.5206,
                            "observed_over": 0.4328}]}
    chk = be.total_level_check([_bet(i, 0.085 if i % 2 else 0.095) for i in range(10)],
                               fitted=fitted)
    assert chk["fires"]
    s = chk["caveat"]
    for want in ("on 10 totals", "9.0 pts", "10 positive-edge Overs",
                 "priced 52.1%", "hit 43.3%"):
        assert want in s, want
    assert chr(0x2014) not in s and chr(0x2013) not in s


# ---------------------------------------------------------------------------
# 7. the page
# ---------------------------------------------------------------------------
def test_the_page_renders_the_lean_on_the_slot_the_badge_and_the_board():
    js = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")
    assert "p.total_level_caveat" in js
    assert "best.total_level_caveat" in js
    assert "d.total_level_check" in js
