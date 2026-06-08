# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guard for Time Machine POINT-IN-TIME org resolution.

The Time Machine is an explicitly point-in-time view, so a prospect's logo there
must be the org they were on AS OF the referenced snapshot — not their current
org (which the live/Statcast surfaces correctly show). The consensus exporter now
stamps each point with its point-in-time org (`points[].org`), resolved from the
historical sources that carry it (FanGraphs' per-snapshot org; per-team list
labels like "… Astros Top 30"); the board resolves the logo from that.

These tests pin the invariant so it can't silently regress back to current org:
  * the _pit_org resolver math (FanGraphs > fresh team label > forward-fill > gap);
  * the data carries the historical org (Whitley 2023 → HOU, current is NOT HOU);
  * the JS board resolves the logo from the point (best.org), with a gap slot;
  * the live/Statcast surface still uses the current-org resolver (unchanged).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "prospx" / "index.html"


def _snap(source, date, org=None, label=""):
    return NS(source=source, snapshot_date=date, org=org, interval_label=label)


# --------------------------------------------------------------------------- #
# Backend unit — deterministic, no DB. Pins the resolution priority.
# --------------------------------------------------------------------------- #
def test_pit_org_prefers_fangraphs_point_in_time():
    import consensus
    snaps = [_snap("fangraphs", "2023-02-23", "HOU", "2023report"),
             _snap("mlb_pipeline", "2023-01-22", "TBR", "MLB Pipeline 2023 Astros Top 30")]
    assert consensus._pit_org(snaps, "2023-02-23") == "HOU"


def test_pit_org_parses_team_label_not_current_org():
    """No FanGraphs → parse the org from the per-team list LABEL, NOT the snapshot's
    org field (which stamps the current org, TBR)."""
    import consensus
    snaps = [_snap("mlb_pipeline", "2023-01-22", "TBR", "MLB Pipeline 2023 Astros Top 30")]
    assert consensus._pit_org(snaps, "2023-01-22") == "HOU"


def test_pit_org_prefers_fresh_at_date_over_stale_forward_fill():
    """A prospect traded TEX→WSN: the stale FanGraphs forward-fill still says TEX,
    but a list freshly published at the date names the new org → WSN wins."""
    import consensus
    snaps = [_snap("fangraphs", "2025-07-31", "TEX", "2025updated"),
             _snap("mlb_pipeline", "2026-01-22", "TEX", "MLB Pipeline 2026 Nationals Top 30")]
    assert consensus._pit_org(snaps, "2026-01-22") == "WSN"
    # ... and before the new list, the forward-fill correctly holds TEX.
    assert consensus._pit_org(snaps[:1], "2025-12-01") == "TEX"


def test_pit_org_gap_returns_none_not_current():
    """No point-in-time signal (Top-100 label has no team, no FanGraphs) → None,
    so the UI shows a neutral placeholder instead of a wrong current-org logo."""
    import consensus
    snaps = [_snap("mlb_pipeline", "2017-01-22", "TBR", "MLB Pipeline 2017 Top 100")]
    assert consensus._pit_org(snaps, "2017-01-22") is None


# --------------------------------------------------------------------------- #
# Data — the exported points carry the historical org (skips pre-regeneration).
# --------------------------------------------------------------------------- #
def _load(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])


@pytest.fixture(scope="module")
def players():
    pros = _load(ROOT / "data" / "timeseries.json")
    grads = _load(ROOT / "data" / "debuts.json")
    if pros is None or grads is None:
        pytest.skip("data exports not present")
    by_key = {p["player_key"]: p for p in (pros + grads) if p.get("player_key")}
    has_org = any(pt.get("org") for p in by_key.values() for pt in (p.get("points") or []))
    if not has_org:
        pytest.skip("points lack point-in-time org — re-run the consensus pipeline")
    return by_key


def test_whitley_2023_point_is_astros_and_differs_from_current(players):
    if "forrest_whitley" not in players:
        pytest.skip("whitley absent")
    w = players["forrest_whitley"]
    pts = [pt for pt in (w.get("points") or []) if str(pt.get("snapshot_date") or "").startswith("2023")]
    assert pts, "no 2023 snapshot for Whitley"
    for pt in pts:
        assert pt.get("org") == "HOU", f"2023 point org {pt.get('org')} != HOU (Astros)"
    assert w.get("org") != "HOU", "current org should differ (he is not an Astro now)"


def test_traded_prospect_point_org_tracks_the_snapshot(players):
    """Abimelec Ortiz: TEX in his Rangers years, WSN from his 2026 trade snapshot."""
    if "abimelec_ortiz" not in players:
        pytest.skip("ortiz absent")
    o = players["abimelec_ortiz"]
    by_date = {pt.get("snapshot_date"): pt.get("org") for pt in (o.get("points") or [])}
    rangers_era = [v for d, v in by_date.items() if d and d < "2026-01-22"]
    nats_era = [v for d, v in by_date.items() if d and d >= "2026-01-22"]
    assert rangers_era and all(v == "TEX" for v in rangers_era), f"pre-trade org not TEX: {rangers_era}"
    assert nats_era and all(v == "WSN" for v in nats_era), f"post-trade org not WSN: {nats_era}"


def test_no_point_silently_uses_a_bogus_org(players):
    """Every non-null point org is a real 2-4 char code (never a leaked label)."""
    bad = []
    for p in players.values():
        for pt in (p.get("points") or []):
            o = pt.get("org")
            if o is not None and not (isinstance(o, str) and 2 <= len(o) <= 4 and o.isupper()):
                bad.append((p["player_key"], pt.get("snapshot_date"), o))
    assert not bad, f"non-code point orgs: {bad[:6]}"


# --------------------------------------------------------------------------- #
# JS source guards — board uses point-in-time; live surface untouched.
# --------------------------------------------------------------------------- #
def test_js_board_resolves_point_in_time_org():
    src = INDEX.read_text(encoding="utf-8")
    m = re.search(r"function _boardAsOf\(.+?\n\}", src, re.S)
    assert m, "_boardAsOf not found"
    body = m.group(0)
    assert "best.org" in body, "_boardAsOf must resolve org from the point-in-time snapshot (best.org)"
    assert "tm-org-gap" in src, "gap placeholder (tm-org-gap) missing"


def test_js_live_statcast_surface_still_uses_current_org():
    """Guardrail: the live/Statcast career table keeps the current-org resolver —
    point-in-time resolution must not leak into it."""
    src = INDEX.read_text(encoding="utf-8")
    assert "_seasonOrgForRow(player, s.season)" in src, \
        "live Statcast surface lost its current-org resolver"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
