# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A traded player must store his SEASON TOTAL, not his last stint.

stats.fetch_sabermetrics is season-scoped (the URL carries season={season}), so more
than one split never means more than one season. It means STINTS: StatsAPI returns the
season aggregate first, marked with numTeams and carrying no team block, then one row
per club. The original code read splits[-1] under the comment "last in list is usually
most recent season slice", which is the LAST STINT for anyone traded mid-season.

Measured against the live API 2026-07-31 for mlbam 672275: the season total is wRC+ 53.2
with 0.204 WAR, the final San Francisco leg is wRC+ 14.8 with -0.156 WAR. A player who
was never traded has exactly one split, so both readings agree, which is how this
survived. It is not cosmetic: prospx renders this wRC+ as a headline chip.

These tests stub the HTTP layer so they are offline and deterministic.
"""
from __future__ import annotations

import stats


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _payload(splits):
    return {"stats": [{"splits": splits}]}


def _split(stat, *, num_teams=None, team=None):
    s = {"stat": stat}
    if num_teams is not None:
        s["numTeams"] = num_teams
    if team is not None:
        s["team"] = {"abbreviation": team}
    return s


TOTAL = {"wRcPlus": 53.2, "woba": 0.281, "war": 0.204}
LEG_A = {"wRcPlus": 92.5, "woba": 0.318, "war": 0.36}
LEG_B = {"wRcPlus": 14.8, "woba": 0.188, "war": -0.156}


def _fetch(monkeypatch, splits, is_pitcher=False):
    monkeypatch.setattr(stats.requests, "get",
                        lambda *a, **k: _Resp(_payload(splits)))
    return stats.fetch_sabermetrics("someone", 672275, 2026, is_pitcher=is_pitcher)


def test_traded_hitter_stores_the_season_total_not_the_last_stint(monkeypatch):
    rec = _fetch(monkeypatch, [
        _split(TOTAL, num_teams=2),
        _split(LEG_A, team="CLE"),
        _split(LEG_B, team="SFG"),
    ])
    assert rec is not None
    assert rec.wrc_plus == 53.2, (
        f"stored {rec.wrc_plus}: that is a single stint. The season aggregate is the "
        "split carrying numTeams, and it comes FIRST, not last.")
    assert rec.war == 0.2
    assert rec.woba == 0.281


def test_aggregate_is_found_even_if_it_is_not_first(monkeypatch):
    """Defend the rule rather than the observed ordering. The fix selects on the
    numTeams marker, so a future API that reorders splits still resolves."""
    rec = _fetch(monkeypatch, [
        _split(LEG_A, team="CLE"),
        _split(LEG_B, team="SFG"),
        _split(TOTAL, num_teams=2),
    ])
    assert rec.wrc_plus == 53.2, rec


def test_untraded_hitter_is_unchanged(monkeypatch):
    """The single-split case must be byte-identical to the old behaviour. This is
    what made the defect invisible: it only ever fired on traded players."""
    only = {"wRcPlus": 150.8, "woba": 0.421, "war": 2.155}
    rec = _fetch(monkeypatch, [_split(only)])
    assert (rec.wrc_plus, rec.woba, rec.war) == (150.8, 0.421, 2.15)


def test_traded_pitcher_also_gets_the_season_total(monkeypatch):
    """The same splits[-1] read fed every pitcher field too, so the fix has to
    cover FIP, xFIP, FIP-, ERA- and WAR, not just the hitter chip."""
    total = {"xfip": 3.80, "fip": 3.75, "fipMinus": 92.0, "eraMinus": 95.0, "war": 1.8}
    leg = {"xfip": 5.90, "fip": 6.10, "fipMinus": 148.0, "eraMinus": 155.0, "war": -0.4}
    rec = _fetch(monkeypatch, [
        _split(total, num_teams=2), _split(leg, team="SFG"),
    ], is_pitcher=True)
    assert (rec.fip, rec.xfip, rec.fip_minus, rec.era_minus, rec.war) == (
        3.75, 3.8, 92.0, 95.0, 1.8)


def test_no_splits_still_returns_none(monkeypatch):
    assert _fetch(monkeypatch, []) is None
