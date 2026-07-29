# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Market-model guards: the two-numbers discipline, NPV math, QO tax
structure, ex-ante $/WAR carry, comps realness, and the Gate-2 artifact
contract. Pure unit tests — no network."""

from __future__ import annotations

import pytest

import fa_market as fm


def test_pos_groups():
    assert fm._pos_group("SP") == "SP" and fm._pos_group("RHP/DH") == "SP"
    assert fm._pos_group("CL") == "RP" and fm._pos_group("C") == "C"
    assert fm._pos_group("SS") == "POS" and fm._pos_group(None) == "POS"


def test_rational_value_is_npv_not_sticker():
    """v2 — seasons price CONVEXLY through the platform tier curve scaled
    to the winter $/WAR level. The NPV properties still hold (a decayed
    path is worth less than a flat one), and the convexity contract is
    stated as math: one season prices at exactly the rescaled tier value,
    and a 3-WAR season is worth more than three 1-WAR seasons."""
    from value_framework import _config as vf_config, tiered_war_value_usd
    flat = fm.rational_value_usd([2.0, 2.0, 2.0, 2.0], 2027, 10_000_000)
    decayed = fm.rational_value_usd([2.0, 1.6, 1.2, 0.8], 2027, 10_000_000)
    assert decayed < flat
    level = 10_000_000 / float(vf_config()["dollars_per_war"]["flat"])
    assert fm.rational_value_usd([1.0], 2027, 10_000_000) == int(
        tiered_war_value_usd(1.0) * level)
    one = fm.rational_value_usd([1.0], 2027, 10_000_000)
    three = fm.rational_value_usd([3.0], 2027, 10_000_000)
    assert three > 3 * one


def test_deal_verdict_bands():
    """Verdict edges sit on the corpus terciles. T1.4 re-derivation
    (2026-07-25, same change as the convexity correction): 109 / 223, from
    corpus terciles under the mean-of-the-value pricing (n=1,300; p33 108.8,
    p67 222.9). Was 75 / 160 under value-of-the-mean, and leaving those in
    place would have re-graded 202 of 1,300 historical contracts on
    arithmetic alone. Value above, overpay below, market between; None
    passes through."""
    assert fm.deal_verdict(None) is None
    assert fm.deal_verdict(400) == "value"
    assert fm.deal_verdict(fm.VERDICT_VALUE_MIN) == "value"
    assert fm.deal_verdict(fm.VERDICT_VALUE_MIN - 1) == "market"
    assert fm.deal_verdict(fm.VERDICT_OVERPAY_MAX) == "market"
    assert fm.deal_verdict(fm.VERDICT_OVERPAY_MAX - 1) == "overpay"
    assert fm.deal_verdict(0) == "overpay"
    assert fm.VERDICT_OVERPAY_MAX < fm.VERDICT_VALUE_MIN


def test_deferral_npv_and_coverage():
    """WS-2a: the deferral ledger prices Ohtani at the platform rate
    (~$197M NPV at 9% — deliberately harsher than CBT's ~4.4%), level
    deals pass through, and the >=200M coverage audit has no holes."""
    npv, had = fm.npv_guarantee_usd("shohei_ohtani", 2024, 700_000_000)
    assert had and 180_000_000 < npv < 215_000_000, npv
    npv2, had2 = fm.npv_guarantee_usd("aaron_judge", 2023, 360_000_000)
    assert not had2 and npv2 == 360_000_000          # explicit-none keeps sticker
    npv3, had3 = fm.npv_guarantee_usd("nobody_ever", 2020, 50_000_000)
    assert not had3 and npv3 == 50_000_000
    # schedule totals are rescaled to the sticker before discounting
    sched_entry = fm._deferral_ledger()["max_scherzer:2015"]
    total = sum(r["amount_usd"] for r in sched_entry["schedule"])
    assert abs(total - 210_000_000) / 210_000_000 < 0.02
    audit = fm.deferral_coverage_audit(
        [{"player_key": "shohei_ohtani", "class_year": 2024,
          "guarantee_usd": 700_000_000, "mlb_deal": True, "player_name": "X"},
         {"player_key": "mystery_mega", "class_year": 2024,
          "guarantee_usd": 250_000_000, "mlb_deal": True, "player_name": "Y"}])
    assert audit["covered"] == 1
    assert audit["missing"][0]["key"] == "mystery_mega:2024"


def test_winter_dpw_methods():
    """flat-carry is the measured winner (data/dpw_forecast_eval.json) and
    the default SHAPE: the most recent PRIOR winter escalated one year. The
    RATE is the module's own de-staling estimate (fm._destale_rate on the
    supplied series), not value_framework's dollars_per_war_inflation --
    that knob is 0.0 in production for a prospect-side reason and silently
    made this carry a no-op (measured 2026-07-24: winter_dpw(2027) ==
    winter_dpw(2028) == winter_dpw(2026), byte-identical). The fitted trend
    candidates stay implemented + callable."""
    series = {2020: 10e6, 2021: 11e6, 2022: 12e6, 2023: 13e6, 2024: 14e6}
    rate = fm._destale_rate(series, 2025)
    assert 0.08 < rate < 0.09                       # log-linear on 10 -> 14 over 4y
    flat = fm.winter_dpw(series, 2025)
    assert flat == pytest.approx(14e6 * (1 + rate))
    trend = fm._fit_log_trend(series, with_cbt=False)(2025)
    assert 13e6 < trend < 17e6


def test_destale_rate_is_ex_ante_and_bounded():
    """The de-staling rate is estimated from the winters it is GIVEN, so a
    caller that hands it a train-only series gets an ex-ante rate. Fewer
    than four winters falls back to the configured knob."""
    grow = {2020: 10e6, 2021: 11e6, 2022: 12e6, 2023: 13e6, 2024: 14e6}
    # winters AFTER the class year never enter the estimate
    assert fm._destale_rate(grow, 2023) == fm._destale_rate(
        {y: v for y, v in grow.items() if y <= 2023}, 2023)
    assert fm._destale_rate(grow, 2023) != fm._destale_rate(grow, 2025)
    assert fm._destale_rate({2023: 10e6, 2024: 11e6}, 2025) == fm._dpw_inflation()
    fall = {2020: 14e6, 2021: 13e6, 2022: 12e6, 2023: 11e6, 2024: 10e6}
    assert fm._destale_rate(fall, 2025) == 0.0      # never de-stales backwards
    spike = {2020: 1e6, 2021: 5e6, 2022: 20e6, 2023: 60e6, 2024: 200e6}
    assert fm._destale_rate(spike, 2025) == 0.12    # clamped


def test_deferral_npv_discounts_schedule():
    sched = [{"year_offset": 0, "amount_usd": 10_000_000},
             {"year_offset": 10, "amount_usd": 90_000_000}]   # Ohtani-shaped
    d = fm.deferral_npv_usd(sched, 100_000_000)
    assert d["sticker_usd"] == 100_000_000
    assert d["npv_usd"] < 60_000_000                          # heavy deferral haircut
    nod = fm.deferral_npv_usd(None, 50_000_000)
    assert nod["npv_usd"] == nod["sticker_usd"] == 50_000_000
    assert "no_deferral_schedule" in nod["method"]


def test_opt_out_scenarios_are_labeled_not_priced():
    s = fm.opt_out_scenarios([3.0, 2.5, 2.0, 1.5], opt_out_after=2,
                             class_year=2027, dpw_usd=12_000_000)
    assert s["pre_opt_out_rational_usd"] < s["full_term_rational_usd"]
    assert "not option-priced" in s["note"]


def test_winter_dpw_is_ex_ante():
    """A winter must never see its own prices: the level is the most
    recent PRIOR winter escalated, even when the winter exists in the
    series."""
    series = {2024: 15_000_000.0, 2025: 16_600_000.0}
    got = fm.winter_dpw(series, 2026)
    assert got == pytest.approx(16_600_000 * 1.05, rel=1e-6)
    # 2025 must anchor on 2024, not itself
    assert fm.winter_dpw(series, 2025) == pytest.approx(15_000_000 * 1.05, rel=1e-6)


def test_qo_tax_prices_picks_in_dollars():
    tax = fm.qo_tax_usd("cbt_payor", "2025-12-15")
    assert tax["total_usd"] > 5_000_000            # two picks + $1M intl pool
    assert len(tax["detail"]) == 2
    assert all(d["surplus_usd"] >= 0 for d in tax["detail"])
    other = fm.qo_tax_usd("other", "2025-12-15")
    assert other["total_usd"] < tax["total_usd"]   # CBT payors pay the most


def test_comps_are_real_prior_contracts():
    pool = [{"player_name": f"P{i}", "class_year": 2020 + (i % 3),
             "position": "SS", "to_team": "NYM", "years": 3 + (i % 4),
             "guarantee_usd": 30_000_000 + i * 1_000_000, "aav_usd": 10_000_000,
             "_war_path": {"war_y1": 2.0 + (i % 5) * 0.3}, "_age": 28 + (i % 6)}
            for i in range(20)]
    target = {"player_name": "Target", "class_year": 2024, "position": "2B",
              "_war_path": {"war_y1": 2.6}, "_age": 30}
    cs = fm.comps_for(target, pool)
    assert 0 < len(cs) <= 5
    names = {p["player_name"] for p in pool}
    assert all(c["player_name"] in names for c in cs)         # never fabricated
    assert all(c["class_year"] <= target["class_year"] for c in cs)


# ---- HARD GATE 2 artifact -----------------------------------------------------

def test_gate2_artifact_committed_and_passing():
    """Ship/no-ship: surfaces may not consume market predictions unless the
    persisted market-gate artifact passes, with the misses published."""
    import json
    from pathlib import Path
    path = Path(__file__).parent / "data" / "fa_gate2_eval.json"
    if not path.exists():
        pytest.skip("market gate not yet run on this machine")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["pass"] is True, f"GATE 2 FAILING: {row['gates']}"
    assert all(row["gates"].values())
    assert row["pooled"]["guarantee"]["n"] > 1000
    assert len(row["biggest_misses"]) >= 10        # honesty surface populated
    assert "forward-chained" in " ".join(row["notes"])
