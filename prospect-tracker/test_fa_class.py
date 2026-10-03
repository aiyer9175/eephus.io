# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Class-construction + ledger guards (pure unit tests, no network)."""

from __future__ import annotations

import pytest

import fa_class as fc
import fa_ident


# ---- option-exercise heuristic (v1, documented) ------------------------------

def test_ufa_is_locked():
    assert fc.exercise_probability({"fa_type": "ufa"}) == {"enter_prob": 1.0, "method": "locked"}


def test_opt_out_walks_when_market_beats_option():
    # Market anchor $30M vs $20M opt-out price -> strongly enters the class.
    row = {"fa_type": "opt_out", "option_price_usd": 20_000_000,
           "market_value_aav_usd": 30_000_000}
    p = fc.exercise_probability(row)
    assert p["method"] == "heuristic_logistic_v1" and p["enter_prob"] > 0.8


def test_club_option_declined_when_overpriced():
    # Club holds a $25M option on a ~$10M player -> club declines -> enters.
    row = {"fa_type": "club_option", "option_price_usd": 25_000_000,
           "prev_war": 0.8}
    p = fc.exercise_probability(row)
    assert p["enter_prob"] > 0.8


def test_club_option_exercised_on_bargain():
    # $8M option on a 4-WAR player -> club keeps him -> stays OUT of class.
    row = {"fa_type": "club_option", "option_price_usd": 8_000_000,
           "prev_war": 4.0}
    p = fc.exercise_probability(row)
    assert p["enter_prob"] < 0.2


def test_anchor_fallback_chain_uses_prev_aav():
    # No market value, no prev WAR -> the player's own AAV anchors.
    row = {"fa_type": "opt_out", "option_price_usd": 55_300_000,
           "prev_aav_usd": 42_000_000}
    p = fc.exercise_probability(row)
    assert p["method"] == "heuristic_logistic_v1" and p["enter_prob"] < 0.2


def test_no_anchor_is_explicit_unknown():
    p = fc.exercise_probability({"fa_type": "opt_out", "option_price_usd": 10_000_000})
    assert p["enter_prob"] is None and p["method"] == "insufficient_data"


def test_mutual_option_uses_documented_prior():
    p = fc.exercise_probability({"fa_type": "mutual_option", "option_price_usd": 1})
    assert p["method"] == "mutual_prior"
    assert p["enter_prob"] == fc.get_config()["class_construction"]["mutual_option_decline_prob"]


# ---- retrospective ledger -----------------------------------------------------

_SIGNING = {"class_year": 2024, "years": 4, "guarantee_usd": 80_000_000,
            "mlb_deal": True, "player_key": "test_player", "player_name": "Test Player"}


def test_ledger_realized_vs_paid(monkeypatch):
    # Pin $/WAR at a flat $10M for arithmetic transparency.
    monkeypatch.setattr(fc, "dollars_per_war_for_season", lambda s, c=None: 10_000_000.0)
    led = fc.ledger_for_signing(_SIGNING, {"2024": 3.0, "2025": 1.0}, current_season=2026)
    assert led["elapsed_years"] == 2 and led["total_years"] == 4
    assert led["war_to_date"] == 4.0
    assert led["realized_value_usd"] == 40_000_000
    assert led["paid_to_date_usd"] == 40_000_000      # level proration: 80M * 2/4
    assert led["surplus_to_date_usd"] == 0
    assert led["complete"] is False


def test_ledger_missing_elapsed_season_counts_zero(monkeypatch):
    """A signed player with NO WAR row in an elapsed season produced
    nothing that year — the ledger scores 0 for it (honest), but a player
    with no WAR resolution at all is skipped (never ghost-scored)."""
    monkeypatch.setattr(fc, "dollars_per_war_for_season", lambda s, c=None: 10_000_000.0)
    led = fc.ledger_for_signing(_SIGNING, {"2024": 2.0}, current_season=2026)
    assert led["war_to_date"] == 2.0                  # 2025 absent -> 0
    assert fc.ledger_for_signing(_SIGNING, None, current_season=2026) is None


def test_ledger_skips_milb_and_unstarted_deals():
    assert fc.ledger_for_signing({**_SIGNING, "mlb_deal": False}, {"2024": 1.0}) is None
    assert fc.ledger_for_signing({**_SIGNING, "class_year": 2030}, {}, current_season=2026) is None


def test_dpw_prefers_estimated_series(monkeypatch):
    """When the Stage-3 market model has written the per-winter $/WAR
    series, the ledger uses IT — the exact season when present, the
    nearest winter escalated otherwise."""
    series = {2024: 15_000_000.0, 2026: 15_300_000.0}
    monkeypatch.setattr(fc, "_dpw_series", lambda: series)
    assert fc.dollars_per_war_for_season(2026) == 15_300_000.0
    # 2028 absent -> nearest (2026) escalated two years at 5%
    assert fc.dollars_per_war_for_season(2028) == pytest.approx(
        15_300_000 * 1.05 ** 2, rel=1e-6)


def test_dpw_backcast_fallback_deescalates(monkeypatch):
    """Without the estimated series (fresh checkout, pre-gate), the
    documented v1 fallback backcasts the framework flat rate."""
    monkeypatch.setattr(fc, "_dpw_series", lambda: {})
    cur = fc.dollars_per_war_for_season(2026, current_season=2026)
    old = fc.dollars_per_war_for_season(2015, current_season=2026)
    assert cur > old > 0
    # 11 years of the framework's configured escalation
    assert old == pytest.approx(cur / (1.05 ** 11), rel=1e-6)


# ---- double-listing dedup (Spotrac option + post-decline UFA rows) -----------

def test_double_listed_option_rows_deduped_option_wins():
    rows = [
        {"player_key": "ryan_mountcastle", "spotrac_id": "17652", "fa_type": "ufa"},
        {"player_key": "ryan_mountcastle", "spotrac_id": "17652", "fa_type": "club_option"},
    ]
    out = fc.dedupe_double_listings(rows)
    assert len(out) == 1 and out[0]["fa_type"] == "club_option"
    # order-independent: option first, UFA second collapses the same way
    out2 = fc.dedupe_double_listings(rows[::-1])
    assert len(out2) == 1 and out2[0]["fa_type"] == "club_option"


def test_distinct_players_never_deduped():
    rows = [
        {"player_key": "a_guy", "spotrac_id": "1", "fa_type": "ufa"},
        {"player_key": "b_guy", "spotrac_id": "2", "fa_type": "ufa"},
        {"player_key": "c_guy", "spotrac_id": None, "fa_type": "club_option"},
    ]
    assert len(fc.dedupe_double_listings(rows)) == 3


# ---- identity alias seam (read-time, never a DB remap) -----------------------
#
# Measured against the real war_daily frames on 2026-08-07: of the five 2027
# members with no price, exactly ONE was a defect. Baseball-Reference spells
# Jake Junis "Jakob Junis" (mlb_ID 596001, 40 IP this season), so the name-keyed
# index missed him and he shipped looking like a man who had not pitched in the
# majors in four years. Woo Jin An (KBO, no affiliated record) and Rowan Wick
# (last MLB season 2022) are correct nulls, and the point of the reason codes
# below is that the artifact now says which is which.

WINDOW = range(2023, 2027)

#: {normalized name: {mlbam: {"years": set, "war": {}}}}, the war_daily_index
#: shape. Years are the real ones.
_FAKE_INDEX = {
    "jakob_junis": {596001: {"years": {2023, 2024, 2025, 2026}, "war": {}}},
    "rowan_wick": {592858: {"years": {2018, 2019, 2020, 2021, 2022}, "war": {}}},
}


@pytest.fixture
def fake_index(monkeypatch):
    """No network: fa_ident's index is the only thing that touches B-Ref."""
    monkeypatch.setattr(fa_ident, "war_daily_index", lambda: _FAKE_INDEX)


def test_the_alias_resolves_our_spelling_to_brefs(fake_index):
    assert fa_ident.resolve("Jakob Junis", WINDOW) == 596001, "sanity"
    assert fa_ident.resolve("Jake Junis", WINDOW) == 596001, (
        "our class spells him Jake; the alias map is what carries that to "
        "B-Ref's Jakob, and without it he prices as unresolved")


def test_an_alias_can_only_add_a_resolution_never_move_one(monkeypatch):
    """The alias is tried ONLY after our own spelling misses. If B-Ref ever
    carries both spellings as different men, the direct match still wins and
    nobody's career silently migrates."""
    idx = dict(_FAKE_INDEX)
    idx["jake_junis"] = {111111: {"years": {2025}, "war": {}}}
    monkeypatch.setattr(fa_ident, "war_daily_index", lambda: idx)
    assert fa_ident.resolve("Jake Junis", WINDOW) == 111111


def test_alias_entries_are_normalized_keys_on_both_sides():
    """The map is keyed on normalize_key OUTPUT, not on display names. A raw
    "Jakob Junis" value would never match an index key and would look like the
    fix was applied when it was not. normalize_key is not idempotent (it eats
    the separators it just wrote), so the round trip goes through the display
    form."""
    from scrapers import normalize_key
    for ours, theirs in fa_ident.NAME_ALIASES.items():
        for key in (ours, theirs):
            assert key == key.lower() and " " not in key
            assert normalize_key(key.replace("_", " ")) == key
        assert ours != theirs


def test_the_three_ways_to_miss_are_reported_apart(fake_index):
    """A KBO entrant, a retired veteran and a spelling bug all returned a bare
    None, so /fa/ told the reader to go looking for a defect in two cases where
    there was none."""
    assert fa_ident.resolve_with_reason("Woo Jin An", WINDOW) == (
        None, fa_ident.NO_MLB_RECORD)
    assert fa_ident.resolve_with_reason("Rowan Wick", WINDOW) == (
        None, fa_ident.NO_RECORD_IN_WINDOW)
    assert fa_ident.resolve_with_reason("Jake Junis", WINDOW) == (
        596001, fa_ident.RESOLVED)


def test_two_men_of_one_name_in_the_window_is_refused_not_guessed(monkeypatch):
    idx = {"jake_junis": {1: {"years": {2024}, "war": {}},
                          2: {"years": {2025}, "war": {}}}}
    monkeypatch.setattr(fa_ident, "war_daily_index", lambda: idx)
    assert fa_ident.resolve_with_reason("Jake Junis", WINDOW) == (
        None, fa_ident.IDENTITY_AMBIGUOUS)


def test_every_reason_code_has_a_reader_facing_sentence():
    """The artifact joins a member's noProj code to unprojected_reason_text. A
    code with no sentence ships a blank explanation next to a blank price."""
    import fa_export
    for code in (fa_ident.NO_MLB_RECORD, fa_ident.NO_RECORD_IN_WINDOW,
                 fa_ident.IDENTITY_AMBIGUOUS):
        assert code in fa_export.NO_PROJ_REASONS
        # The sentence is served copy, and the owner's copy rule is lint-gated.
        assert "—" not in fa_export.NO_PROJ_REASONS[code]


# ---- M04-04: the realized ledger names its WAR basis -------------------------

def test_build_ledger_stamps_the_war_basis_it_was_given(monkeypatch):
    """The Archive labelled every realized figure eWAR while the stored ledger
    was a June 2026 bWAR build (1,429 of 1,429 rows equal the bWAR sum). A row
    now carries the basis its WAR map came from, so the label can follow it."""
    monkeypatch.setattr(fc, "dollars_per_war_for_season", lambda s, c=None: 10_000_000.0)
    classes = {2024: {"signed": [_SIGNING]}}
    wbk = {"test_player": {"seasons": {"2024": 3.0, "2025": 1.0}, "source": "ewar_v2"}}
    rows = fc.build_ledger(classes, wbk, current_season=2026)
    assert rows[0]["ledger"]["war_basis"] == "ewar_v2"
    assert rows[0]["ledger"]["built"]


def test_the_war_map_source_names_the_displayed_basis_explicitly():
    """Until the fWAR label epoch the stamp followed the facade default. Since step
    D + U (2026-10-03) the default is the training label (fWAR) while the Archive's
    realized WAR is a displayed number that stays eWAR v2 (owner answer EPOCH-Q4), so
    the frames are read on provider "ewar_v2" by name and the stamp names the same
    series; never a hardcoded "bbref". Queue 7 M14 chooses the provider for its
    post-epoch rebuild on fWAR (owner answer M14-3) explicitly when it runs."""
    from pathlib import Path
    src = (Path(__file__).parent / "fa_pipeline.py").read_text(encoding="utf-8")
    assert '"source": "bbref"' not in src
    assert '"source": war_source.DEFAULT_PROVIDER' not in src
    body = src.split("def _resolve_signed_via_war_daily", 1)[1].split("\ndef ", 1)[0]
    assert 'war_source.stint_frame(side, provider="ewar_v2")' in body
    assert '"source": "ewar_v2"' in body


def test_served_archive_labels_follow_its_war_basis():
    import json
    from pathlib import Path
    here = Path(__file__).parent
    arc = json.loads((here / "data" / "fa_archive.json").read_text(encoding="utf-8"))
    meta = json.loads((here / "data" / "fa_meta.json").read_text(encoding="utf-8"))
    assert arc.get("warBasis") in ("bwar", "ewar_v2", "mixed")
    assert meta.get("archive_war_basis") == arc["warBasis"]
    js = (here / "assets" / "fa.js").read_text(encoding="utf-8")
    assert "Realized eWAR" not in js, "a realized label is hardcoded to eWAR"
    assert js.count("${realizedWar()}") >= 5
    dpw = (here / "assets" / "fa_dpw.js").read_text(encoding="utf-8")
    assert "REALIZED_WAR = j.archive_war_basis" in dpw
