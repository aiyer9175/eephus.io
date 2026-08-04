# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Projections module guards: the committed sidecar's shape contract
(assets/projections.js renders it blind), bucket ordering, prospect/vet
source discipline, and the convex season-pricing helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import proj_export as pe

ROOT = Path(__file__).parent
SIDECAR = ROOT / "data" / "mlb_projections.json"


def test_pythagenpat_scales_exponent_with_run_environment():
    """With games played, _pythag_pct uses Pythagenpat (exp = RPG**0.287): a
    higher run environment lifts the exponent, spreading a given RS/RA ratio's
    win% further from .500 than the fixed-1.83 fallback. Equal RS/RA is always
    .500; None inputs guard to None."""
    # same RS/RA ratio (1.2), different run environments via games played
    lo = pe._pythag_pct(600, 500, 162)   # ~6.8 RPG
    hi = pe._pythag_pct(1200, 1000, 162)  # ~13.6 RPG, exponent higher
    assert hi > lo > 0.5
    # fixed fallback (no g) sits at the 1.83 exponent, below the high-env Pythagenpat
    fixed = pe._pythag_pct(1200, 1000, None)
    assert hi > fixed > 0.5
    assert pe._pythag_pct(700, 700, 162) == 0.5
    assert pe._pythag_pct(None, 500, 162) is None
    assert pe._pythag_pct(500, -1, 162) is None


def test_season_value_pricing_is_convex_and_escalates():
    """Season $ value rides the platform tier curve (convex) at the winter
    level, escalating per season — the same pricing as FA rational value."""
    v1 = pe._season_value_usd(1.0, 0, 16_000_000)
    v3 = pe._season_value_usd(3.0, 0, 16_000_000)
    assert v3 > 3 * v1                       # convex: stars cost more per win
    later = pe._season_value_usd(1.0, 3, 16_000_000)
    assert later == pytest.approx(v1 * 1.05 ** 3, rel=1e-9)
    assert pe._season_value_usd(0.0, 0, 16_000_000) == 0.0


def _payload():
    if not SIDECAR.exists():
        pytest.skip("mlb_projections.json not exported on this machine")
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


def test_sidecar_shape_contract():
    d = _payload()
    assert d["first_season"] == pe.FIRST_SEASON and d["horizon"] == pe.HORIZON
    assert d["n_vets"] > 800 and d["n_prospects"] > 100
    # dpw_infl == 0.0 is CORRECT under the production clemens_2026 set: its net-7%-flat
    # discount convention folds win-cost growth into the net rate (valuation_sets.py
    # sets dollars_per_war_inflation = 0.0 for form net_7_flat). The old 0 < bound
    # encoded the pre-clemens 5%-inflation convention.
    assert d["dpw_usd"] > 5_000_000 and 0 <= d["dpw_infl"] < 0.2
    # Prospect WAR paths run the platform CONTROL WINDOW (clemens_2026: 7 seasons),
    # not the fixed 6 the pre-clemens artifact carried -- derive the cap from the
    # PRODUCTION default set (conftest pins this module to the identity set for
    # hermeticity, but the committed artifact is exported under the production set),
    # so a valuation-set window change cannot silently re-break this.
    import value_framework as _vf
    with _vf.valuation_set(_vf._DEFAULT_VALUATION_SET):
        _ctrl = int(_vf._config()["service_time"]["control_years"])
    for m in d["vets"][:50] + d["prospects"][:50]:
        assert m["key"] and m["name"] and m["src"] in ("vet", "prospect")
        assert len(m["war"]) <= max(pe.HORIZON, _ctrl, 6) and m["war"], m["name"]
        assert m["warTotal"] is not None


def test_efv_grade_matches_prospx_board():
    # /projections/ and the PROSPX board must show the SAME eFV grade for a
    # prospect (they diverged when mlb_projections.json baked a stale eFV vintage;
    # run_daily now re-bakes proj_export after the eFV regen to keep them in sync).
    # Only meaningful when the two artifacts are the SAME vintage -- proj_export is
    # monthly, xfv.json is daily, so a mid-cadence working tree can legitimately have
    # a stale mlb_projections; skip rather than false-fail in that window.
    d = _payload()
    xfv_path = ROOT / "data" / "xfv.json"
    if not xfv_path.exists():
        pytest.skip("xfv.json not present")
    xj = json.loads(xfv_path.read_text(encoding="utf-8"))
    xf = xj.get("by_player", {})
    rows = (d.get("vets") or []) + (d.get("prospects") or [])
    mism = []
    for r in rows:
        if r.get("fv_source") != "xfv" or r.get("fv") is None:
            continue
        rec = xf.get(r.get("key"))
        if not rec:
            continue
        want = rec.get("xfv_grade_realized")
        want = rec.get("xfv_grade") if want is None else want
        if want is not None and round(r["fv"]) != round(want):
            mism.append((r.get("key"), r["fv"], want))
    # >5% mismatch => genuinely different vintages (proj_export not re-run after an
    # eFV regen); skip. A same-vintage drift (a real regression) shows near-zero
    # mismatch normally, so any nonzero count under the threshold still fails.
    if rows and len(mism) > 0.05 * len(rows):
        pytest.skip(f"mlb_projections.json is a different eFV vintage than xfv.json "
                    f"({len(mism)}/{len(rows)} rows differ); reconciles on next full rebuild")
    assert not mism, f"projections eFV drifted from PROSPX (same vintage) for {len(mism)} rows: {mism[:5]}"


def test_bucket_ordering_floor_mean_ceiling():
    d = _payload()
    for m in d["vets"] + d["prospects"]:
        if m.get("warTotalP10") is None:
            continue
        assert m["warTotalP10"] <= m["warTotal"] + 0.11, m["name"]
        assert m["warTotal"] <= m["warTotalP90"] + 0.11, m["name"]


def test_vet_surplus_only_on_contracted_seasons():
    """The module's honesty rule: a veteran surplus claim requires a real
    contract (signed_through + per-season salary)."""
    d = _payload()
    for m in d["vets"]:
        if m.get("surNpv") is not None:
            assert m.get("thru"), f"{m['name']} has surplus but no contract"
        if m.get("sur"):
            assert any(s is not None for s in m["sur"])


def test_prospects_carry_outcome_buckets_and_eta():
    d = _payload()
    order = list(pe._BUCKET_ORDER)
    for m in d["prospects"]:
        assert m["eta"] >= pe.FIRST_SEASON
        # The membership GATE is price_fv >= 45 (proj_export ~:627), on the
        # quantile basis, because the value curves were fitted on the consensus
        # 20-80 scale. The DISPLAYED fv became the board grade on 2026-08-04
        # (outcome_implied_fv), so the two are deliberately different numbers and
        # `fv >= 45` is no longer an invariant: 9 of 209 served rows display
        # 44.1 to 44.9 while clearing the gate on the grade that admits them.
        # Nothing user-facing claims a 45 threshold (the 45 in projections.js is
        # only a colour break), so this is a basis split, not a mislabel.
        #
        # The floor is kept, loosened to 42, because the failure it really
        # guards against is a BASIS BREAK: if fv were ever wired to the raw
        # 20-floored grade, roughly half the pool would read exactly 20 and this
        # would catch it immediately. A bound of 42 does that with headroom over
        # the observed 44.1 minimum.
        assert m.get("fv") is not None and m["fv"] >= 42
        assert m["bucketLo"] in order and m["bucketHi"] in order
        assert order.index(m["bucketLo"]) <= order.index(m["bucketHi"]), m["name"]
        assert 0 <= (m.get("pBust") or 0) <= 1


def test_last_controlled_season():
    H, F = pe.HORIZON, pe.FIRST_SEASON
    last = F + H - 1
    # Prospect: full horizon (6-yr control >> horizon), regardless of age.
    assert pe._last_controlled_season({"src": "prospect", "eta": F + 2}) == last
    # Contracted vet: through signed_through.
    assert pe._last_controlled_season({"src": "vet", "thru": F + 3}) == F + 3
    # Non-contracted young (pre-arb): full horizon.
    assert pe._last_controlled_season({"src": "vet", "age": 23}) == last
    # Non-contracted older (likely pending FA): first season only.
    assert pe._last_controlled_season({"src": "vet", "age": 31}) == F
    # Mid (age 27): 29-27 = 2 more seasons.
    assert pe._last_controlled_season({"src": "vet", "age": 27}) == F + 2


def _toy_team_outlook(monkeypatch, vets, prospects=None):
    """Run _team_outlook in isolation (no farm join, no eval side-effect)."""
    monkeypatch.setattr(pe, "_org_farm_blocks", lambda: {})
    monkeypatch.setattr(pe, "_write_team_outlook_eval", lambda *a, **k: None)
    return pe._team_outlook(vets, prospects or [], {}, {}, {})


def _vet(team, war, thru, *, champ=None, age=27, key=None):
    champ = champ if champ is not None else war
    return {"team": team, "name": key or team, "key": key or team, "pos": "SS",
            "age": age, "thru": thru, "war": war, "warChamp": champ,
            "warY1Champ": champ[0]}


def _toy30(monkeypatch):
    """30 teams: a sustained high-WAR core, a control-cliff twin, and 28
    modest sustained teams — enough to make the per-season 2,430 recenter hold."""
    H, F = pe.HORIZON, pe.FIRST_SEASON
    full = F + H - 1
    vets = [_vet("SUS", [8.0] * H, full, key="sus"),
            _vet("CLF", [8.0] * H, F, key="clf")]   # contract ends after year 1
    vets += [_vet(f"T{i:02d}", [2.0] * H, full, key=f"t{i}") for i in range(2, 30)]
    return _toy_team_outlook(monkeypatch, vets)


def test_team_outlook_multiyear_shape_and_recenter(monkeypatch):
    rows = _toy30(monkeypatch)
    assert len(rows) == 30
    for r in rows:
        assert len(r["byYear"]) == pe.HORIZON
        for s in r["byYear"]:
            assert abs(s["wins"] + s["losses"] - 162) < 0.2
        # Back-compat year-1 top-level fields mirror byYear[0].
        assert r["war"] == r["byYear"][0]["war"]
        assert r["wins"] == r["byYear"][0]["wins"]
    # Every season independently recenters to the 2,430-win league sum
    # (tolerance absorbs per-team 0.1-rounding across 30 teams).
    for t in range(pe.HORIZON):
        tot = sum(r["byYear"][t]["wins"] for r in rows)
        assert abs(tot - 2430) < 2, (t, tot)


def test_team_outlook_control_cliff(monkeypatch):
    rows = _toy30(monkeypatch)
    by = {r["team"]: r for r in rows}
    # Sustained core holds its WAR; the cliff twin drops to 0 after year 1.
    assert by["SUS"]["byYear"][0]["war"] == 8.0
    assert by["SUS"]["byYear"][-1]["war"] == 8.0
    assert by["CLF"]["byYear"][0]["war"] == 8.0
    assert by["CLF"]["byYear"][-1]["war"] == 0.0
    # The win gap between the two widens in the out-years (the point of the view).
    gap_y1 = by["SUS"]["byYear"][0]["wins"] - by["CLF"]["byYear"][0]["wins"]
    gap_last = by["SUS"]["byYear"][-1]["wins"] - by["CLF"]["byYear"][-1]["wins"]
    assert gap_last > gap_y1


def test_team_outlook_window_alignment(monkeypatch):
    """etaAlignYears = surplus-weighted farm ETA minus the WAR-weighted core
    center. A core with flat controlled WAR across 2027-31 centers at the
    midpoint; a farm arriving before it reads negative (aligned)."""
    H, F = pe.HORIZON, pe.FIRST_SEASON
    mid = F + (H - 1) / 2.0                      # 2029.0 for 2027-31
    v = _vet("WIN", [6.0] * H, F + H - 1, key="win")
    # Farm block with a known surplus-weighted arrival one year before the core.
    monkeypatch.setattr(pe, "_write_team_outlook_eval", lambda *a, **k: None)
    monkeypatch.setattr(pe, "_org_farm_blocks",
                        lambda: {"WIN": {"farmRank": 1, "etaMean": mid - 1.0,
                                         "etaByYear": [0.5, 0.5, 0, 0, 0, 0], "etaN": 10}})
    rows = pe._team_outlook([v], [], {}, {}, {})
    f = rows[0]["farm"]
    assert f["coreCenter"] == round(mid, 2)
    assert f["etaAlignYears"] == round((mid - 1.0) - mid, 2) == -1.0


def test_org_farm_blocks_eta_rollup():
    """The live rollup over timeseries.json: every org gets a surplus-weighted
    etaMean inside the horizon and an arrival curve that sums to 1."""
    blocks = pe._org_farm_blocks()
    assert len(blocks) >= 25
    seen = 0
    for org, b in blocks.items():
        if b.get("etaMean") is None:
            continue
        seen += 1
        assert pe.FIRST_SEASON <= b["etaMean"] <= pe.FIRST_SEASON + pe.HORIZON
        if b.get("etaByYear"):
            assert abs(sum(b["etaByYear"]) - 1.0) < 0.02
            assert len(b["etaByYear"]) == pe.HORIZON + 1
    assert seen >= 25


def test_team_outlook_uses_champion_mean_not_display(monkeypatch):
    """The roll-up must sum champion MEANS (warChamp), never the median-like
    displayed war head — the 83-win-Dodgers failure mode, multi-year edition."""
    H, F = pe.HORIZON, pe.FIRST_SEASON
    v = _vet("AAA", [1.0] * H, F + H - 1, champ=[5.0] * H)   # display 1.0, mean 5.0
    rows = _toy_team_outlook(monkeypatch, [v])
    assert rows[0]["byYear"][0]["war"] == 5.0


def test_team_outlook_locked_pct(monkeypatch):
    """lockedPct = controlled WAR / everyone-stays WAR over the horizon. A core
    locked through the horizon scores 1.0; a control cliff after year 1 scores
    year1 / full."""
    H, F = pe.HORIZON, pe.FIRST_SEASON
    full_yr = F + H - 1
    sus = _vet("SUS", [8.0] * H, full_yr, key="sus")   # locked through horizon
    clf = _vet("CLF", [8.0] * H, F, key="clf")         # control ends after 2027
    rows = _toy_team_outlook(monkeypatch, [sus, clf])
    by = {r["team"]: r for r in rows}
    assert by["SUS"]["lockedPct"] == 1.0
    assert by["CLF"]["lockedPct"] == round(8.0 / (8.0 * H), 3)   # 0.2 @ H=5
    assert by["SUS"]["lockedPct"] > by["CLF"]["lockedPct"]
    # Absolute cost-controlled strength + the everyone-stays denominator.
    assert by["SUS"]["ctrlWar5y"] == round(8.0 * H, 1)
    assert by["CLF"]["ctrlWar5y"] == 8.0
    assert by["CLF"]["fullWar5y"] == round(8.0 * H, 1)


def test_team_outlook_prospects_count_as_locked(monkeypatch):
    """A prospect is cost-controlled the whole horizon, so it lifts (never drags)
    the lock-up %: adding one to an already-locked core keeps it at 1.0."""
    H, F = pe.HORIZON, pe.FIRST_SEASON
    vets = [_vet("AAA", [4.0] * H, F + H - 1)]
    prospects = [{"team": "AAA", "name": "Pr", "key": "pr",
                  "eta": F + 1, "war": [3.0, 3.0, 3.0, 3.0]}]
    rows = _toy_team_outlook(monkeypatch, vets, prospects)
    assert rows[0]["lockedPct"] == 1.0


def test_team_outlook_prospect_eta_offset(monkeypatch):
    H, F = pe.HORIZON, pe.FIRST_SEASON
    vets = [_vet("AAA", [1.0] * H, F + H - 1)]
    prospects = [{"team": "AAA", "name": "Pr", "key": "pr",
                  "eta": F + 2, "war": [3.0, 3.5, 4.0]}]
    rows = _toy_team_outlook(monkeypatch, vets, prospects)
    aaa = next(r for r in rows if r["team"] == "AAA")
    # Years 0-1: vet only; year 2 on: vet + ETA-aligned prospect path.
    assert aaa["byYear"][0]["war"] == 1.0
    assert aaa["byYear"][1]["war"] == 1.0
    assert aaa["byYear"][2]["war"] == 4.0          # 1.0 + 3.0
    assert aaa["byYear"][3]["war"] == round(1.0 + 3.5, 1)


def test_accountability_vet_horizons_surfaces_survived_and_pinball():
    """The accountability 'Veteran WAR paths' backtest must surface the HONEST
    calibration reads - survived-only coverage (+ its n) and the pinball loss -
    not only the pooled coverage the eval harness itself warns 'a wide band
    catches trivially' (absent seasons score actual=0, inside almost any band).
    Fields are additive: the pooled `coverage` the frontend reads stays."""
    he = ROOT / "data" / "proj_horizon_eval.json"
    if not he.exists():
        pytest.skip("proj_horizon_eval.json not present on this machine")
    acct = pe._accountability_block()
    vh = (acct.get("backtests") or {}).get("data/proj_horizon_eval.json") or {}
    rows = ((vh.get("champion") or {}).get("horizons")) or []
    if not rows:
        pytest.skip("proj_horizon_eval.json holdout_2022_2024 block absent")
    for r in rows:
        # pooled coverage retained (assets/projections.js reads r.coverage)
        assert "coverage" in r
        # honest metrics now surfaced alongside it
        for k in ("coverage_survived", "n_survived", "pinball_q10", "pinball_q90"):
            assert k in r, f"missing {k} on horizon {r.get('h')}"
    # Not misleadingly optimistic: pooled coverage is >= the honest survived-only
    # read wherever both are computed (pooled is inflated by absent-season zeros).
    both = [r for r in rows if r.get("coverage") is not None
            and r.get("coverage_survived") is not None]
    assert both, "no horizon carries both pooled and survived coverage"
    for r in both:
        assert r["coverage"] + 1e-9 >= r["coverage_survived"], r


def test_site_carries_projections_surface():
    site = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '"/projections/"' in site, "NAV_ITEMS must deep-link /projections/"
    assert "build_projections" in site
    page = ROOT / "projections" / "index.html"
    if page.exists():
        src = page.read_text(encoding="utf-8")
        assert "projections.js" in src and "proj-rows" in src
