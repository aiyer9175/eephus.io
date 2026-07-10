# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guard for the Statcast/stats meta-surface Org column.

Bug (2026-06): the per-season Org column resolves org via _seasonOrgForRow, which
walks trade history backward with YEAR granularity. A current-year OFFSEASON trade
(e.g. 2026-02-09 BOS->MIL) looked like a mid-season trade, so the current-season
row was rolled back to the pre-trade org (showing the OLD team) for every player
traded in the offseason — diverging from the canonical current org that home pages
and the transactions log show.

Fix: the current season short-circuits to the canonical current org (player.org);
past seasons keep the trade-history walk untouched (historical attribution must
not shift). These tests pin both halves of that invariant.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "prospx" / "index.html"
CUR = datetime.date.today().year


def _season_org(player: dict, season: int) -> str | None:
    """Faithful Python port of prospx `_seasonOrgForRow` (post-fix). The rendered
    Org column must agree with this — the current season is the canonical current
    org, past seasons fold backward through trade history."""
    if not player or season is None:
        return None
    org = player.get("org") or None
    if season >= CUR:                       # current season -> canonical current org
        return org
    trades = sorted((player.get("trades") or []), key=lambda t: t.get("trade_date") or "")
    for t in reversed(trades):
        td = t.get("trade_date")
        if not td:
            continue
        ty = int(str(td)[:4])
        if ty > season:
            org = t.get("from_org") or org
        elif ty == season:
            org = t.get("from_org") or org
        else:
            break
    return org


def test_js_keeps_current_season_shortcircuit():
    """Source guard: the career-table org resolver must short-circuit the
    CURRENT season to the canonical current org. Dropping this re-introduces
    the stale-org bug for current-year-traded players. (_seasonOrgForRow was
    retired in favor of the stat-line point-in-time resolver inside
    _careerOrgAndStints; the current-season exception lives there now.)"""
    src = INDEX.read_text(encoding="utf-8")
    m = re.search(r"function _careerOrgAndStints\(.+?\n\}", src, re.S)
    assert m, "_careerOrgAndStints not found in prospx/index.html"
    body = m.group(0)
    assert "getFullYear()" in body and re.search(r"season\s*>=\s*new Date\(\)\.getFullYear\(\)", body), \
        "current-season short-circuit (season >= getFullYear()) missing from the career-table org resolver"


def test_js_stat_row_has_row_aware_org_meta_helper():
    """Stats-board rows must render orgs through row-aware metadata rather than
    blindly using the player's current org."""
    src = INDEX.read_text(encoding="utf-8")
    assert "_statRowOrgMetaHTML" in src, "row-aware stats-board org meta helper missing"
    assert "_statRowOrgMetaHTML(p, r)" in src, \
        "leaderboard/player meta rows must use row-aware org rendering"


def test_js_uses_row_org_before_any_current_org_fallback():
    """Graduates with legacy org-less rows (Giolito/Buehler class) should not
    stamp every historical season with today's org. Refreshed row.org wins and
    ambiguous historical rows stay unresolved instead of being guessed."""
    src = INDEX.read_text(encoding="utf-8")
    assert "function _playerOrgEvents(" in src, "transaction/acquisition org timeline missing"
    assert "function _eventOrgSplitForSeason(" in src, "transaction split resolver missing"
    assert re.search(r"if \(row && row\.org\)\s*\{", src), \
        "stats row org must be trusted before inferred fallback"
    assert "stints.length === 1 ? stints[0].org : (s && s.org)" in src, \
        "career table must read the season's own stat-line org"
    assert "Org unresolved in this season's stat data" in src, \
        "ambiguous historical career rows must render as unresolved"
    assert "_seasonOrgForRow(player" not in src, \
        "retired current-org trade-walk resolver must not return"


def _load(path: Path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])


@pytest.fixture(scope="module")
def players():
    grads = _load(ROOT / "data" / "debuts.json")
    pros = _load(ROOT / "data" / "timeseries.json")
    if grads is None or pros is None:
        pytest.skip("data exports (debuts.json / timeseries.json) not present")
    return {p["player_key"]: p for p in (grads + pros) if p.get("player_key")}


def test_current_season_org_equals_canonical_for_trade_cohort(players):
    """For EVERY player traded in the current season, the meta Org for the current
    season equals the canonical current org (player.org) — so the Statcast surface
    agrees with home pages + the transactions log."""
    cohort = [p for p in players.values()
              if any(str(t.get("trade_date") or "")[:4] == str(CUR) for t in (p.get("trades") or []))]
    assert cohort, "no current-season trade cohort found in the data"
    bad = [(p["player_key"], _season_org(p, CUR), p.get("org"))
           for p in cohort if _season_org(p, CUR) != (p.get("org") or None)]
    assert not bad, f"{len(bad)} traded players show a stale current-season org (got, want): {bad[:6]}"


def test_named_cohort(players):
    """The reported examples — graduates + prospects — match their home-page org."""
    expect = {"kyle_harrison": "MIL", "mackenzie_gore": "TEX", "caleb_durbin": "BOS",
              "devin_fitzgerald": "WSN", "abimelec_ortiz": "WSN"}
    missing = [k for k in expect if k not in players]
    if missing:
        pytest.skip(f"named players absent from data: {missing}")
    for k, org in expect.items():
        p = players[k]
        assert _season_org(p, CUR) == org == (p.get("org") or None), \
            f"{k}: meta org {_season_org(p, CUR)} != canonical {p.get('org')} (want {org})"


def test_historical_attribution_preserved(players):
    """The fix must NOT shift any PAST season's org (ranking-integrity guardrail):
    Kyle Harrison's 2025 line stays SFG (accrued before his mid-2025 trade), not
    his current MIL."""
    h = players.get("kyle_harrison")
    if not h:
        pytest.skip("kyle_harrison absent from data")
    assert _season_org(h, 2025) == "SFG"
    assert _season_org(h, 2024) == "SFG"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
