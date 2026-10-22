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
    # The control-window keys (2026-09-17). `ctrlThru` is the last season the
    # club CONTROLS him, derived once in salary_path.control_end; `salThru` is
    # the last season the path PRICES him, and they are different objects on
    # hundreds of rows. Every surface reads the first and none of them
    # recomputes it, so the shape contract is where it has to be pinned.
    _ctrl_rows = [m for m in d["vets"] if m.get("ctrlThru") is not None]
    assert _ctrl_rows, "no vet row carries a control window"
    for m in _ctrl_rows:
        assert isinstance(m["ctrlThru"], int)
        assert m["ctrlThru"] >= (m.get("thru") or 0)
        assert m["ctrlThru"] >= (m.get("salThru") or 0)
        assert m.get("ctrlWhy") in (None, "prearb_grid", "no_prior_salary",
                                    "closure_buyout", "horizon", "contract_only")
        # omitted rather than shipped false: the payload carries 1,120 vet rows
        for k in ("ctrlOpen", "ctrlEst"):
            assert m.get(k) in (None, True), (m["key"], k)
    for m in d["prospects"]:
        assert m.get("ctrlThru") is None, m["key"]


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
    # VINTAGE GUARD, measured DIRECTLY off the build stamps both artifacts already
    # carry (both are date.today().isoformat(): proj_export.build_payload ~:2001
    # writes the sidecar's top-level generated_at, efv_export.run ~:162 writes
    # xfv.json's meta.generated_at), instead of being inferred from a mismatch
    # count. Note proj_export.py carries three date.today() stamps (:1489, :1957,
    # :2001) and efv_export.py two (:162, :333); the two cited here are the ones
    # this test actually reads, so a line-number drift is checkable.
    #
    # The count-based guard this replaces ("skip when >5% of rows differ") could
    # never detect the skew it was written for, because its denominator was EVERY
    # row in the sidecar while only a small slice is comparable at all: a row has
    # to carry fv_source == "xfv" AND appear in xfv.json's by_player. Measured
    # 2026-08-07 on a genuinely skewed pair: 1,528 rows, 201 comparable, 60 of
    # those 201 drifted 0.1 to 1.1 FV and 8 broke the round-to-nearest tolerance.
    # The guard therefore saw 8 against a 76.4-row threshold (0.5%) and let a
    # whole-vintage skew fail as though it were a same-vintage regression.
    #
    # REFUTED, do not re-chase: this is NOT floor routing reaching one side and
    # not the other. route_floor_grade overwrites xfv_grade inside
    # efv_score.run_live (~:2068) BEFORE the served entry dict is built (~:2110);
    # efv_export._entry then copies that one value into both xfv_grade and
    # xfv_grade_realized (identical on 9,382 of 9,382 rows); 0 rows carry
    # xfv_grade_model_raw and ENABLED_DEFAULT is False, so efv_board_scale.
    # board_value cannot diverge either. proj_export._board_grade (~:872) and the
    # PROSPX board (prospx/index.html ~:32534) resolve the SAME field, so
    # proj_export inherits routing and needs no rule of its own.
    #
    # The real driver is artifact vintage. data/xfv.json is committed, so the
    # standing post-wave "revert data/" discipline git-restores it, while
    # data/mlb_projections.json is gitignored (.gitignore:46) and is not, which
    # leaves the sidecar one local rebuild ahead of the board it is compared to.
    proj_vintage = d.get("generated_at")
    xfv_vintage = (xj.get("meta") or {}).get("generated_at")
    if not proj_vintage or not xfv_vintage:
        # Cannot establish the single-vintage precondition, so the invariant is
        # undefined. The reason string names the missing stamp so a renamed key
        # shows up as a readable skip rather than as a silently passing test.
        pytest.skip(f"cannot establish a single eFV vintage: mlb_projections.json "
                    f"generated_at={proj_vintage!r}, xfv.json meta.generated_at="
                    f"{xfv_vintage!r}")
    if proj_vintage != xfv_vintage:
        pytest.skip(f"different eFV vintages: mlb_projections.json generated_at="
                    f"{proj_vintage}, xfv.json meta.generated_at={xfv_vintage}. "
                    f"The projections/PROSPX parity invariant is only defined on a "
                    f"single vintage; reconciles on the next full rebuild.")
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
    # Vintage was already established as single above, so ANY mismatch here is a
    # real same-vintage regression. No count tolerance: one drifted row means the
    # two surfaces would show a user two different eFV grades for one player.
    assert not mism, f"projections eFV drifted from PROSPX (same vintage) for {len(mism)} rows: {mism[:5]}"


def test_bucket_ordering_floor_mean_ceiling():
    d = _payload()
    for m in d["vets"] + d["prospects"]:
        if m.get("warTotalP10Comon") is None:
            continue
        assert m["warTotalP10Comon"] <= m["warTotal"] + 0.11, m["name"]
        assert m["warTotal"] <= m["warTotalP90Comon"] + 0.11, m["name"]


def test_vet_surplus_only_on_priced_seasons():
    """The module's honesty rule, widened with the thing it is honest ABOUT.

    A veteran surplus claim rests on a PRICE for each season it covers: a real
    contract (signed_through + per-season salary), or - since GATE C
    (2026-08-09) and across the whole control window since ask C (2026-09-16) -
    the salary path: the CBA league minimum for a pre-arbitration season and the
    arbitration board's projected award for an arbitration season. Those rows
    are stamped salSrc and the board says so ("arb est."). A surplus claim on
    NEITHER is the defect this guards, and it is the same defect as before; only
    the set of things that count as a price got bigger.

    RENAMED from test_vet_surplus_only_on_contracted_seasons, because the old
    name stopped describing the rule the moment the league minimum became a
    price - and a test whose name lies is worse than no test."""
    d = _payload()
    for m in d["vets"]:
        if m.get("surNpv") is not None:
            assert (m.get("thru")
                    or m.get("salSrc") in ("arb_projection", "contract+arb")
                    or m.get("salPath")), (
                f"{m['name']} has surplus but no contract and no salary path")
        if m.get("sur"):
            assert any(s is not None for s in m["sur"])
        # A cut season carries no surplus, by construction: surNpv is the NPV of
        # the non-null entries, so the two have to agree to the dollar.
        if m.get("salCut") is not None:
            t0 = m["salCut"] - d["first_season"]
            assert all(s is None for s in (m.get("sur") or [])[t0:]), m["key"]
        # and nothing is priced past the end of club control.
        if m.get("salThru") is not None:
            assert max(s[0] for s in m["salPath"]) == m["salThru"], m["key"]


def test_the_salary_path_census_is_published_with_the_payload():
    """A $8.8B coverage move that cannot say what it reached is a claim. The
    census says what it priced, from which source, what it could not reach and
    why, and which board vintage it read."""
    d = _payload()
    cen = ((d.get("accountability") or {}).get("salary_path") or {})
    assert cen, "the accountability block carries no salary_path census"
    assert cen.get("mode") in ("off", "ladder", "closure", "full")
    assert cen.get("vintage")
    assert "stale" in cen
    if cen["mode"] != "off":
        for k in ("salary_path_rows", "salary_path_seasons", "truncated",
                  "cliff_rows", "cliff_first_season", "prearb_negative_seasons"):
            assert k in cen, k


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
    # AND IT IS NOT THE FIELD ANY SURFACE READS. This function is the Team
    # Outlook control cliff and it stays on the age proxy (decision D5): for a
    # pre-arb 23-year-old it returns the full horizon while the salary path,
    # which is what the board prints, ends where the grid ends. The surfaces
    # read `ctrlThru`. If this ever becomes the displayed window, it has to be
    # a measured change with the Team Outlook blast radius priced, not a quiet
    # re-point - so the disagreement is asserted rather than assumed.
    import salary_path as _sp
    _path = {"last_controlled": F + 1, "truncated": None,
             "closure_buyout": False, "src_mix": "arb_ladder"}
    assert pe._last_controlled_season({"src": "vet", "age": 23}) == last
    assert _sp.control_end(_path, None, F, H)["end"] == F + 1
    assert _sp.control_end(_path, None, F, H)["end"] != pe._last_controlled_season(
        {"src": "vet", "age": 23})


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


def test_zero_path_receipt_copies_the_sweep_run_s2():
    """SWEEP-Q2 (owner 2026-10-22): the Veteran WAR paths receipts carry a
    zero-path column copied from the null comparator sweep's run S2, both
    engines on the same rows, and nothing when a cell is missing or the two
    engines disagree on the zero path (different rows)."""
    def cell(mae, zero, verdict):
        return {"n": 10, "mae_model": mae, "nulls": {"ZERO": {
            "mae_null": zero, "verdict": verdict, "lo95": -0.1, "hi95": 0.1}},
            "instrument": {"verdict": "PASS"}}
    sweep = {"generated_at": "2026-10-22T04:31:36Z", "registration": "docs/NULL_COMPARATOR_SWEEP.md",
             "runs": {"S2": {"frame": "row-matched, bases [2017, 2018, 2019, 2021], horizons 1-5",
                             "label": "fwar", "n_players_matched": 10, "cells": {
                 "challenger_proj_lgbm": {"h1": cell(0.4, 0.6, "BEATS"), "h4": cell(0.33, 0.34, "TIES"),
                                          "pooled_h1_h5": cell(0.3, 0.4, "BEATS")},
                 "champion_decay": {"h1": cell(0.5, 0.6, "BEATS"), "h4": cell(0.36, 0.34, "LOSES"),
                                    "pooled_h1_h5": cell(0.4, 0.4, "TIES")}}}}}
    zp = pe._zero_path_receipt(sweep)
    assert zp["bases"] == [2017, 2018, 2019, 2021] and zp["label"] == "fwar"
    assert zp["models"] == ["proj_lgbm_v1", "marcel_decay_v2"]
    assert [r["h"] for r in zp["by_horizon"]] == [1, 4]          # pooled is not a horizon
    h4 = zp["by_horizon"][1]
    assert h4["mae"] == {"proj_lgbm_v1": 0.33, "marcel_decay_v2": 0.36, "zero": 0.34}
    assert h4["vs_zero"]["marcel_decay_v2"]["verdict"] == "LOSES"
    sweep["runs"]["S2"]["cells"]["champion_decay"]["h4"]["nulls"]["ZERO"]["mae_null"] = 0.35
    assert pe._zero_path_receipt(sweep) == {}
    assert pe._zero_path_receipt({}) == {}


def test_zero_path_receipt_matches_the_committed_sweep():
    path = ROOT / "data" / "null_comparator_sweep.json"
    if not path.exists():
        pytest.skip("null_comparator_sweep.json not present")
    sweep = json.loads(path.read_text(encoding="utf-8"))
    zp = pe._zero_path_receipt(sweep)
    by_h = {r["h"]: r for r in zp["by_horizon"]}
    assert sorted(by_h) == [1, 2, 3, 4, 5]
    cells = sweep["runs"]["S2"]["cells"]
    for h, r in by_h.items():
        assert r["mae"]["proj_lgbm_v1"] == cells["challenger_proj_lgbm"][f"h{h}"]["mae_model"]
        assert r["mae"]["marcel_decay_v2"] == cells["champion_decay"][f"h{h}"]["mae_model"]
        assert r["mae"]["zero"] == cells["champion_decay"][f"h{h}"]["nulls"]["ZERO"]["mae_null"]
    if (ROOT / "data" / "proj_horizon_eval.json").exists():
        vh = pe._accountability_block()["backtests"]["data/proj_horizon_eval.json"]
        assert vh.get("zero_path") == zp


def test_site_carries_projections_surface():
    site = (ROOT / "build_site.py").read_text(encoding="utf-8")
    assert '"/projections/"' in site, "NAV_ITEMS must deep-link /projections/"
    assert "build_projections" in site
    page = ROOT / "projections" / "index.html"
    if page.exists():
        src = page.read_text(encoding="utf-8")
        assert "projections.js" in src and "proj-rows" in src


# ---------------------------------------------------------------------------
# Team Win Totals card (M05-02, 2026-09-24). The table used to print the
# cohort-intercept challenger arm unconditionally, so after the 2026-08-04 gate
# loss the card scored an arm the roll-up no longer applies, beside a registry
# metric line that said the served arm won and a foot that read "baseline
# retained". One card, three holdout outcomes.
# ---------------------------------------------------------------------------

def _team_outlook_eval() -> dict:
    p = ROOT / "data" / "team_outlook_eval.json"
    if not p.exists():
        pytest.skip("team_outlook_eval.json not present on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def test_team_wins_table_prints_the_arm_the_ship_decision_serves():
    retro = _team_outlook_eval().get("retro_backtest") or {}
    if not retro.get("team_level_per_season"):
        pytest.skip("retro_backtest block absent")
    arm = ("cohort_recentered" if (retro.get("ship_decision") or {}).get("challenger_wins")
           else "recentered")
    # the arm printed is the arm the roll-up applies
    assert (arm == "cohort_recentered") == bool(pe._cohort_intercepts())
    tw = pe._accountability_block()["backtests"]["data/team_outlook_eval.json"]
    assert tw["served_arm"] == arm
    assert tw["retro_generated_at"] == retro.get("generated_at")
    for row, s in zip(tw["per_season"], retro["team_level_per_season"]):
        assert row["season"] == s["season"]
        assert row["mae"] == s[arm]["mae"] and row["r"] == s[arm]["r"], row
        assert row["baseline_mae"] == s["baseline_prior_wins"]["mae"]
        assert row["baseline_r"] == s["baseline_prior_wins"]["r"]


def test_team_wins_arm_follows_the_ship_decision(monkeypatch):
    """Mutation: flip challenger_wins and the printed arm must follow."""
    def fake(name):
        if name != "team_outlook_eval.json":
            return {}
        return {"retro_backtest": {
            "ship_decision": {"challenger_wins": flag},
            "team_level_per_season": [{"season": 2025, "is_holdout": True,
                                       "recentered": {"mae": 1.0, "r": 0.1},
                                       "cohort_recentered": {"mae": 2.0, "r": 0.2},
                                       "baseline_prior_wins": {"mae": 3.0, "r": 0.3}}]}}
    monkeypatch.setattr(pe, "_read_data_json", fake)
    for flag, mae in ((False, 1.0), (True, 2.0)):
        tw = pe._accountability_block()["backtests"]["data/team_outlook_eval.json"]
        assert tw["per_season"][0]["mae"] == mae, (flag, tw)


def test_team_wins_registry_prose_carries_no_unbacked_figure():
    """Every decimal in the registry's metric and baseline lines for this card
    must appear in its eval artifact (DNR 9: accuracy claims derive from an
    artifact). The predicts line's one decimal is the replacement-wins constant."""
    import re
    from rate_stabilization import REPLACEMENT_WINS
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "team_win_projections")
    art = (ROOT / "data" / "team_outlook_eval.json").read_text(encoding="utf-8")
    for field in ("metric", "baseline"):
        for num in re.findall(r"\d+\.\d+", row[field]):
            assert num in art, (field, num)
    assert [float(x) for x in re.findall(r"\d+\.\d+", row["predicts"])] == [REPLACEMENT_WINS]
    assert "bWAR roll-up" not in row["predicts"] and "none yet" not in row["baseline"]


def test_team_wins_foot_reads_the_gate_from_the_artifact():
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    body = src[src.index("function teamWinsTable("):src.index("function vetHorizonsTable(")]
    assert "baseline retained" not in body
    assert "hm.recentered" in body and "hm.cohort_recentered" in body
    assert "s.baseline_r" in body and "tw.served_arm" in body


def test_team_outlook_eval_says_whether_the_vector_serves():
    ev = _team_outlook_eval()
    on = bool(pe._cohort_intercepts())
    assert (ev.get("serve_vector_tripwire") or {}).get("vector_serving") is on
    cal = ev.get("calibration") or {}
    assert cal.get("cohort_intercepts_applied") is on
    assert ("not applied" in cal.get("kind", "")) is (not on)


def test_prospect_statline_flag_is_on_and_off_is_byte_identical(tmp_path, monkeypatch):
    """TL_18 (docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md Part 12, TL-Q6 (a)):
    SERVE_PROSPECT_STATLINE is True after the spent look; off, the exporter never
    calls the statline writer and its mlb_projections.json bytes equal the bytes
    with the flag on; on, the writer runs once, takes no argument from the payload,
    and the file it serves is data/prospect_statline.json beside the others."""
    import inspect
    assert pe.SERVE_PROSPECT_STATLINE is True
    src = inspect.getsource(pe.export)
    assert "if SERVE_PROSPECT_STATLINE:" in src
    assert "import prospect_statline" not in inspect.getsource(pe.build_payload)
    writer_src = inspect.getsource(pe._write_prospect_statline)
    payload = {"vets": [], "prospects": [{"key": "a_prospect"}], "n_vets": 0, "n_prospects": 1,
               "team_outlook": []}
    monkeypatch.setattr(pe, "build_payload", lambda: payload)
    monkeypatch.setattr(pe, "_write_components", lambda vets: None)
    monkeypatch.setattr(pe, "write_futures", lambda rows: 0)
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    calls: list = []
    monkeypatch.setattr(pe, "_write_prospect_statline", lambda: calls.append("written"))
    monkeypatch.setattr(pe, "SERVE_PROSPECT_STATLINE", False)
    pe.export()
    off = (tmp_path / "mlb_projections.json").read_bytes()
    assert calls == []
    monkeypatch.setattr(pe, "SERVE_PROSPECT_STATLINE", True)
    pe.export()
    on = (tmp_path / "mlb_projections.json").read_bytes()
    assert on == off
    assert calls == ["written"]
    import prospect_statline as PSL
    assert PSL.SERVED_PATH.name == "prospect_statline.json"
    assert "PSL.write_served()" in writer_src
