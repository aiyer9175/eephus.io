# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FanGraphs' published WAR as a REFERENCE beside the displayed eWAR v2 on the
MLB player card (owner answer EPOCH-Q4 "Keep eWAR v2 shown", task
EPOCH_FWAR_REFERENCE_COLUMN, after the fWAR label epoch's step Z).

What is pinned:
  (a) no served eWAR number moves: the career rows' `war` and `war_bwar` are
      the same with and without the reference map;
  (b) `war_fwar` equals the 'fwar' provider's value, rounded to 1dp, on every
      cell the frozen vintage publishes, and is ABSENT everywhere else (the
      provider's incumbent fallback is never printed under a FanGraphs label);
  (c) the attribution strings sit in the payload description and in the
      renderer, and no copy calls either WAR more accurate (clause (l));
  (d) the served data/mlb_player_detail.json, when it carries the reference,
      matches the frozen vintage cell for cell (gitignored and rebuilt
      nightly, so this layer skips when the artifact is absent or older).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import milb_history as mh
import mlb_player_export as mpe
import war_source
from test_war_source import _EWAR_FIX, _VINTAGE_FIX, _patched_pybaseball

ROOT = Path(__file__).parent
DETAIL = ROOT / "data" / "mlb_player_detail.json"

NOTE = ("war_fwar = FanGraphs' published WAR (MLB StatsAPI sabermetrics feed), a "
        "reference beside the displayed eWAR v2; absent means no published value")
TIP = ("FanGraphs' published WAR, as MLB's StatsAPI publishes it. A reference only: "
       "the site's WAR is eWAR.")

# StatsAPI season lines for the fixture players (milb_history.player_index shape).
_LINES = {
    ("hitting", 2023): {545361: [{"level": "MLB", "pa": 507}],
                        660271: [{"level": "MLB", "pa": 599}]},
    ("hitting", 2024): {545361: [{"level": "MLB", "pa": 166}],
                        694973: [{"level": "MLB", "pa": 1}]},
    ("pitching", 2023): {660271: [{"level": "MLB", "bf": 531}]},
    ("pitching", 2024): {694973: [{"level": "MLB", "bf": 545}]},
    ("pitching", 2025): {694973: [{"level": "MLB", "bf": 720}]},
}


@pytest.fixture()
def lines(monkeypatch):
    monkeypatch.setattr(mh, "player_index",
                        lambda season, group: _LINES.get((group, season), {}))


def _maps():
    with _patched_pybaseball(_EWAR_FIX, _VINTAGE_FIX):
        served, bwar = mpe._war_maps()
        ref = mpe._fwar_reference_map()
        provider = war_source.side_war_by_season(provider="fwar")
    return served, bwar, ref, provider


def test_the_reference_is_the_provider_on_published_cells_only():
    _served, _bwar, ref, provider = _maps()
    # the published cells, both sides, equal to the provider
    assert ref[660271][2023] == {"bat": 5.95, "pit": 3.04}
    assert ref[545361][2023] == {"bat": 2.81} and ref[545361][2024] == {"bat": 1.7}
    assert ref[694973][2024] == {"pit": 4.27}
    for mid, by in ref.items():
        for season, cell in by.items():
            for side, v in cell.items():
                assert v == provider[mid][season][side], (mid, season, side)
    # the provider serves Skenes 2025 from the incumbent (no vintage row): absent here
    assert provider[694973][2025] == {"pit": 5.6}
    assert 2025 not in ref[694973]
    # the vintage's mixed 2010 season is served by no door
    assert 2010 not in ref.get(545361, {})
    # the 0.0 batting line the provider's blank-row rule skips is absent too
    assert "bat" not in ref[694973][2024]


def test_career_rows_carry_war_fwar_and_leave_the_served_war_alone(lines):
    served, bwar, ref, provider = _maps()
    for mid, is_pit in ((545361, False), (660271, False), (660271, True), (694973, True),
                        (694973, False)):
        before = mpe._career_rows(mid, is_pit, served, bwar)
        after = mpe._career_rows(mid, is_pit, served, bwar, ref)
        assert [r["y"] for r in before] == [r["y"] for r in after]
        for b, a in zip(before, after):
            # (a) the served eWAR and the bWAR reference never move
            assert a["war"] == b["war"] and a.get("war_bwar") == b.get("war_bwar")
            assert {k: v for k, v in a.items() if k != "war_fwar"} == b
            # (b) war_fwar is the provider's published value at 1dp, or absent
            side = "pit" if is_pit else "bat"
            pub = (ref.get(mid, {}).get(a["y"]) or {}).get(side)
            if pub is None:
                assert "war_fwar" not in a, (mid, a["y"], side)
            else:
                assert a["war_fwar"] == round(provider[mid][a["y"]][side], 1)
    rows = {(r["y"]): r for r in mpe._career_rows(694973, True, served, bwar, ref)}
    assert rows[2024]["war"] == 4.6 and rows[2024]["war_bwar"] == 4.3
    assert rows[2024]["war_fwar"] == 4.3            # 4.27 published, at 1dp
    assert "war_fwar" not in rows[2025]              # no published value
    hit = {r["y"]: r for r in mpe._career_rows(694973, False, served, bwar, ref)}
    assert not hit or "war_fwar" not in hit.get(2024, {})


def test_a_missing_vintage_drops_the_reference_not_the_card(monkeypatch):
    def _raise(**_kw):
        raise war_source.DataUnavailable("no vintage")
    monkeypatch.setattr(war_source, "side_war_by_season", _raise)
    assert mpe._fwar_reference_map() == {}


def test_the_served_war_door_reads_the_display_provider():
    import inspect
    body = inspect.getsource(mpe._war_maps)
    assert 'war_source.side_war_by_season(provider=war_source.DISPLAY_PROVIDER)' in body
    ref = inspect.getsource(mpe._fwar_reference_map)
    assert 'side_war_by_season(provider="fwar")' in ref
    assert "fwar_vintage.side_targets(" in ref


def test_the_attribution_strings_are_in_the_payload_and_the_renderer():
    src = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")
    assert NOTE in src
    js = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert f'const FG_WAR_TIP = "{TIP}";' in js
    assert ">FanGraphs WAR</th>" in js
    # clause (l): no accuracy language beside either WAR
    for text in (NOTE, TIP):
        low = text.lower()
        for word in ("accurate", "better", "truer", "closer to the truth", "calibrated"):
            assert word not in low, word


def _served():
    if not DETAIL.exists():
        pytest.skip("data/mlb_player_detail.json is absent (gitignored, rebuilt nightly)")
    d = json.loads(DETAIL.read_text(encoding="utf-8"))
    rows = [(p, r, side) for p in d["players"].values()
            for key, side in (("career", "pit" if p.get("isPit") else "bat"),
                              ("careerPit", "pit"))
            for r in (p.get(key) or [])]
    if not any("war_fwar" in r for _p, r, _s in rows):
        pytest.skip("the served payload predates the fWAR reference column; re-run "
                    "mlb_player_export")
    return d, rows


def test_the_served_payload_names_the_reference():
    d, _rows = _served()
    assert any(NOTE in n for n in d["notes"])


def test_the_served_reference_matches_the_frozen_vintage_cell_for_cell():
    import fwar_vintage
    _d, rows = _served()
    blob = fwar_vintage.load()
    targets = {s: fwar_vintage.side_targets(blob, s) for s in ("bat", "pit")}
    n = 0
    for p, r, side in rows:
        if "war_fwar" not in r:
            continue
        pub = targets[side].get((int(p["mlbam"]), int(r["y"])))
        assert pub is not None, (p["key"], r["y"], side)
        assert r["war_fwar"] == round(pub, 1), (p["key"], r["y"], side)
        n += 1
    assert n > 1000
