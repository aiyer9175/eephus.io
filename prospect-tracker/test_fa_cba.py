# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rule-versioned CBA logic guards.

The contract: every QO/CBT computation resolves rules from dated records,
unknown futures carry forward EXPLICITLY (never silently), and the
pre-history refuses to answer rather than inventing a rule."""

from __future__ import annotations

from datetime import date

import pytest

import fa_cba


def test_regime_resolution_in_window():
    r = fa_cba.regime_as_of("2024-06-15")
    assert r["regime"] == "cba_2022"
    assert r["carry_forward"] is False


def test_regime_carry_forward_past_expiry():
    """2026-12-02 is one day past the 2022 CBA's expiry — the regime
    carries forward WITH the flag the UI banner keys off."""
    r = fa_cba.regime_as_of("2026-12-02")
    assert r["regime"] == "cba_2022"
    assert r["carry_forward"] is True


def test_regime_refuses_prehistory():
    with pytest.raises(LookupError):
        fa_cba.regime_as_of("2010-01-01")


def test_cbt_threshold_known_season():
    t = fa_cba.cbt_threshold(2026)
    assert t["threshold_usd"] == 244_000_000
    assert t["carry_forward"] is False


def test_cbt_threshold_2027_is_explicit_carry_forward():
    t = fa_cba.cbt_threshold(2027)
    assert t["carry_forward"] is True
    assert t["verify_status"] == "explicitly-unknown"
    # carried forward from the last encoded season, never invented
    assert t["threshold_usd"] == fa_cba.cbt_threshold(2026)["threshold_usd"]


def test_cbt_threshold_far_future_still_carries_forward():
    assert fa_cba.cbt_threshold(2030)["carry_forward"] is True


def test_surcharge_tiers_shape():
    tiers = fa_cba.cbt_surcharge_tiers()
    assert tiers == sorted(tiers) and len(tiers) == 3


def test_qo_value_known_and_unknown():
    v = fa_cba.qo_value(2026)
    assert v is not None and v["value_usd"] > 15_000_000
    # 2027's QO value is unannounced — None, not a guess.
    assert fa_cba.qo_value(2027) is None


def test_pick_forfeiture_tiers():
    for tier in (fa_cba.PAYOR_CBT, fa_cba.PAYOR_REVENUE_SHARING, fa_cba.PAYOR_OTHER):
        f = fa_cba.pick_forfeiture(tier, date(2025, 12, 15))
        assert "picks" in f and isinstance(f["picks"], list) and f["picks"]
        assert f["carry_forward"] is False
    # CBT payors forfeit two picks + intl pool money; others forfeit one.
    cbt = fa_cba.pick_forfeiture(fa_cba.PAYOR_CBT, date(2025, 12, 15))
    assert len(cbt["picks"]) == 2 and cbt["intl_pool_usd"] > 0


def test_pick_forfeiture_unknown_tier_raises():
    with pytest.raises(KeyError):
        fa_cba.pick_forfeiture("mystery_tier", date(2025, 12, 15))


def test_qo_acceptances_filter():
    rows_2023 = fa_cba.qo_acceptances(2023)
    assert all(r["class_year"] == 2023 for r in rows_2023)
    assert len(fa_cba.qo_acceptances()) >= len(rows_2023)


def test_unverified_records_surface_for_checkpoint():
    """Curated records stay flagged until the owner spot-checks them —
    the list must be non-empty until verification happens, and the
    function exists precisely so the checkpoint can print it."""
    flagged = fa_cba.unverified_records()
    assert isinstance(flagged, list)
    assert flagged, "curation flags were cleared without owner verification"


def test_draft_r11_threshold_is_read_per_draft_year_from_sourced_records():
    """Owner answer M9M10-1 (b), 2026-10-01: the round 11+ bonus-pool threshold is a
    dated, sourced record per CBA: 125,000 for the 2017-2021 drafts (MLB.com, 2017
    pool article, corroborated 2018, 2019 and by the 2022 change), 150,000 for the
    2022-2026 drafts. A draft past the encoded CBA carries forward, flagged; a draft
    before it raises."""
    fa_cba.reload()
    for y in range(2017, 2022):
        r = fa_cba.draft_r11_threshold(y)
        assert r["threshold_usd"] == 125_000 and r["regime"] == "cba_2017" and not r["carry_forward"], y
    for y in range(2022, 2027):
        r = fa_cba.draft_r11_threshold(y)
        assert r["threshold_usd"] == 150_000 and r["regime"] == "cba_2022" and not r["carry_forward"], y
    late = fa_cba.draft_r11_threshold(2027)
    assert late["carry_forward"] and late["verify_status"] == "explicitly-unknown"
    with pytest.raises(LookupError):
        fa_cba.draft_r11_threshold(2016)
    recs = fa_cba._rules()["draft_r11_bonus_thresholds"]
    assert [(r["first_draft"], r["last_draft"], r["threshold_usd"]) for r in recs] == [
        (2017, 2021, 125_000), (2022, 2026, 150_000)]
    for r in recs:
        assert r["source"].startswith("https://www.mlb.com/news/"), r["regime"]
        assert f"${r['threshold_usd']:,}" in r["clause"], r["regime"]
        assert r["verify_status"] == "source-verified" and r["verified_on"] == "2026-10-01"
        regime = next(g for g in fa_cba._rules()["cba_regimes"] if g["regime"] == r["regime"])
        assert (r["effective_from"], r["effective_to"]) == (regime["effective_from"], regime["effective_to"])
    early = recs[0]
    assert {c["draft"] for c in early["corroboration"]} == {2016, 2018, 2019, 2022}
    assert any("$100,000" in c["quote"] for c in early["corroboration"] if c["draft"] == 2016)
    assert any("from $125,000 to $150,000" in c["quote"] for c in early["corroboration"] if c["draft"] == 2022)
