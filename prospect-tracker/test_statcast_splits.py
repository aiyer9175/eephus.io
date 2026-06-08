# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guard for the Statcast/stats surface MID-SEASON-trade split.

A mid-season (in-season) trade means the player accrued stats at 2+ orgs within
one season. The career fetcher now keeps the per-team stints (career_stats row
carries a `stints` list) and a summed combined total; the stats surface renders
that as a dual-org chip (old -> new) plus an expandable per-org split.

These tests pin the invariants so the behavior can't silently regress:
  * the data-driven signal is `len(row.stints) >= 2` (a real multi-org season);
  * the per-org stints reconcile to the combined season total;
  * the right-hand (new) org is that season's FINAL org — equal to the canonical
    current org when the in-season trade is the player's latest move;
  * OFFSEASON-only trades produce NO stints (single current-org logo, no split) —
    the separate prior offseason fix (test_statcast_org.py) is untouched;
  * the JS keys the dual chip off `s.stints` and falls back to _seasonOrgForRow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "prospx" / "index.html"


def _load(path: Path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])


@pytest.fixture(scope="module")
def players():
    # timeseries.json / debuts.json are gitignored generated artifacts — present
    # locally + after a pipeline run, absent on a fresh checkout (then we skip the
    # data assertions; the backend-unit + JS-source guards below still run).
    pros = _load(ROOT / "data" / "timeseries.json")
    grads = _load(ROOT / "data" / "debuts.json")
    if pros is None or grads is None:
        pytest.skip("data exports (timeseries.json / debuts.json) not present")
    by_key = {p["player_key"]: p for p in (pros + grads) if p.get("player_key")}
    has_splits = any(len(r.get("stints") or []) >= 2
                     for p in by_key.values() for r in (p.get("career_stats") or []))
    if not has_splits:
        pytest.skip("data predates the stint split — re-run the stats pipeline to populate")
    return by_key


# --------------------------------------------------------------------------- #
# Backend unit test — deterministic, no network / no data files. Pins the
# combine-stints math (the source of the per-org split + combined total).
# --------------------------------------------------------------------------- #
def test_combine_stints_reconciles_and_resolves_org():
    import stats

    def split(org, g, ab, h, tb, bb, hbp, sf, pa, so, hr):
        return {"season": 2025, "_level": "MLB", "_level_label": "AL", "_org": org,
                "stat": {"gamesPlayed": g, "atBats": ab, "hits": h, "totalBases": tb,
                         "baseOnBalls": bb, "hitByPitch": hbp, "sacFlies": sf,
                         "plateAppearances": pa, "strikeOuts": so, "homeRuns": hr,
                         "stolenBases": 0, "rbi": 0,
                         "avg": "—", "obp": "—", "slg": "—", "ops": "—"}}
    # Andrew Vaughn's real 2025 stints (CHW then MIL).
    chw = split("CHW", 48, 185, 35, 58, 7, 0, 1, 193, 43, 5)
    mil = split("MIL", 64, 221, 68, 109, 24, 3, 5, 254, 37, 9)
    rows = [stats._row_from_split(chw, False), stats._row_from_split(mil, False)]
    assert [r["org"] for r in rows] == ["CHW", "MIL"]            # per-stint org resolves

    comb = stats._combine_stints([chw, mil], False)
    assert comb["org"] is None                                   # multi-org → chip uses stints
    assert comb["games"] == 112 and comb["ab"] == 406            # counting stats add
    assert comb["avg"] == ".254"                                 # 103/406
    assert comb["obp"] == ".307"                                 # (103+31+3)/(406+31+3+6)
    assert comb["slg"] == ".411"                                 # 167/406
    assert comb["ops"] == ".718"

    # A single-team group never combines (sanity: one stint stays a plain row).
    solo = stats._row_from_split(chw, False)
    assert "stints" not in solo and solo["org"] == "CHW"


def _row(player, season, level):
    for r in player.get("career_stats") or []:
        if r.get("season") == season and r.get("level") == level:
            return r
    return None


def _ip_outs(ip):
    whole, _, frac = str(ip).partition(".")
    return int(whole or 0) * 3 + (int(frac) if frac else 0)


# --------------------------------------------------------------------------- #
# Data: the named cohort carries the right per-org stints (old -> new).
# --------------------------------------------------------------------------- #
def test_named_cohort_split_seasons(players):
    expect = {
        # key:          (season, level, [old, new])
        "leo_de_vries":  (2025, "A+",  ["SDP", "ATH"]),   # prospect (MiLB affiliates)
        "andrew_vaughn": (2025, "MLB", ["CHW", "MIL"]),   # big-leaguer
        "mackenzie_gore": (2022, "AAA", ["SDP", "WSN"]),  # historical mid-season (pitcher)
    }
    missing = [k for k in expect if k not in players]
    if missing:
        pytest.skip(f"named players absent from data: {missing}")
    for key, (season, level, orgs) in expect.items():
        r = _row(players[key], season, level)
        assert r is not None, f"{key}: {season} {level} row missing"
        got = [st.get("org") for st in (r.get("stints") or [])]
        assert got == orgs, f"{key} {season} {level}: stint orgs {got} != {orgs} (old -> new)"


def test_right_hand_org_equals_canonical_current_for_latest_split(players):
    """For a split that IS the player's latest move, the new (right-hand) org
    equals the canonical current org (player.org) — so the chip agrees with home
    pages + transactions."""
    for key, (season, level) in {"leo_de_vries": (2025, "A+"),
                                 "andrew_vaughn": (2025, "MLB")}.items():
        if key not in players:
            pytest.skip(f"{key} absent")
        r = _row(players[key], season, level)
        new_org = (r.get("stints") or [])[-1].get("org")
        assert new_org == players[key].get("org"), \
            f"{key}: right-hand org {new_org} != canonical current {players[key].get('org')}"


def test_historical_split_keeps_that_seasons_final_org(players):
    """A non-latest split row uses that SEASON'S final org, not today's org —
    Gore's 2022 AAA split ends WSN even though he is now TEX."""
    if "mackenzie_gore" not in players:
        pytest.skip("gore absent")
    r = _row(players["mackenzie_gore"], 2022, "AAA")
    assert (r.get("stints") or [])[-1].get("org") == "WSN"
    assert players["mackenzie_gore"].get("org") == "TEX"   # current org differs


# --------------------------------------------------------------------------- #
# Data: stints reconcile to the combined total; signal is len(stints) >= 2.
# --------------------------------------------------------------------------- #
def test_every_stint_set_reconciles_to_combined(players):
    """Every multi-org row's stints sum (games + AB/IP) to the combined line —
    the split surfaces existing data, it never invents a total."""
    checked = 0
    for p in players.values():
        for r in p.get("career_stats") or []:
            stints = r.get("stints")
            if not stints or len(stints) < 2:
                continue
            checked += 1
            g = sum(int(st.get("games") or 0) for st in stints)
            assert g == int(r.get("games") or 0), \
                f"{p['player_key']} {r['season']} {r['level']}: games {g} != {r.get('games')}"
            if r.get("is_pitcher"):
                outs = sum(_ip_outs(st.get("ip")) for st in stints)
                assert outs == _ip_outs(r.get("ip")), \
                    f"{p['player_key']} {r['season']}: IP outs {outs} != {_ip_outs(r.get('ip'))}"
            else:
                ab = sum(int(st.get("ab") or 0) for st in stints)
                assert ab == int(r.get("ab") or 0), \
                    f"{p['player_key']} {r['season']}: AB {ab} != {r.get('ab')}"
    assert checked >= 50, f"expected many split rows in the data, found {checked}"


def test_offseason_only_players_have_no_stints(players):
    """A player whose trades are ALL offseason accrues at one org per season —
    no stints, no spurious split. Durbin (3 offseason trades) is the canary."""
    if "caleb_durbin" not in players:
        pytest.skip("durbin absent")
    for r in players["caleb_durbin"].get("career_stats") or []:
        assert not (r.get("stints") and len(r["stints"]) >= 2), \
            f"durbin {r['season']} {r['level']} sprouted a spurious split"


def test_current_season_offseason_trade_stays_single(players):
    """Gore was traded WSN->TEX in the 2026 OFFSEASON; his 2026 row must stay a
    single org (no split) — the prior offseason fix is not regressed."""
    if "mackenzie_gore" not in players:
        pytest.skip("gore absent")
    r = _row(players["mackenzie_gore"], 2026, "MLB")
    if r is None:
        pytest.skip("gore 2026 row absent")
    assert not r.get("stints"), "gore 2026 (offseason trade) must not have a split"


# --------------------------------------------------------------------------- #
# JS source guards — the render keys off the data-driven stints signal.
# --------------------------------------------------------------------------- #
def test_js_dual_chip_keys_off_stints_with_single_fallback():
    src = INDEX.read_text(encoding="utf-8")
    m = re.search(r"function _careerOrgAndStints\(.+?\n\}", src, re.S)
    assert m, "_careerOrgAndStints not found in prospx/index.html"
    body = m.group(0)
    # data-driven signal: 2+ stints
    assert "s.stints" in body and re.search(r"stints\.length\s*<\s*2", body), \
        "dual chip must key off len(stints) >= 2"
    # single / offseason path still uses the trade-derived single-org resolver
    assert "_seasonOrgForRow(player, s.season)" in body, \
        "single-org fallback must still use _seasonOrgForRow (prior offseason fix)"


def test_js_has_split_toggle_and_rows():
    src = INDEX.read_text(encoding="utf-8")
    assert "data-stint-toggle" in src and "data-stint-rows" in src, \
        "per-org split sub-rows / toggle wiring missing"
    assert "function _toggleStintRows(" in src, "stint expand/collapse handler missing"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
