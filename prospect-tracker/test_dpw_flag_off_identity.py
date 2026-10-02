# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""OFF byte-identity of the $/WAR path build, function level (DESIGN_v2 section 9).

With value_framework.SERVE_DPW_PATH off (the committed default) every
unified-capable function returns exactly what its pre-build body returns. The
pre-build bodies are kept below as VERBATIM copies (docstrings and comment lines
dropped, code unchanged), executed against the live module's helpers, so the
comparison does not drift with the live config, the fitted file or VAL_1's
level. Artifact identity is proven outside pytest by tools/dpw_off_capture.py.

Also here: the switch can only be turned ON by the committed constant (the
environment can only force it off), the bucket cache is keyed on the basis, the
dpw_path_forced callers are on an allowlist, and each stage of the blast-radius
switch moves only its own lever.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

import dpw_testkit as kit
import fa_market as fm
import fa_mc
import proj_export
import value_framework as vf

ROOT = Path(__file__).resolve().parent

# The pre-build bodies (HEAD b3ad2bba), verbatim code.
LEGACY = {
    'value_framework._service_path_surplus_usd': '''
def _service_path_surplus_usd(season_wars: list[float], super_two: bool,
                              eta_years: float = 0.0) -> float:
    markets = [tiered_war_value_usd(w) for w in season_wars]
    salaries = _service_path_salaries(season_wars, markets, super_two)
    cfg = _config()
    infl = float(cfg.get("dollars_per_war_inflation", 0.0))
    r = float(cfg["discount_rate"])
    net = (1.0 + infl) / (1.0 + r)
    return sum((markets[t] - salaries[t]) * (net ** (float(eta_years) + t))
               for t in range(len(season_wars)))
''',
    'value_framework._service_path_salaries': '''
def _service_path_salaries(season_wars: list[float], markets: list[float],
                           super_two: bool) -> list[float]:
    cfg = _config()
    st = cfg["service_time"]
    league_min = float(st["league_min_usd"])
    pre_arb, arb_fracs = _arb_ladder(st, super_two)
    arb_basis = str(st.get("arb_basis", "current_season"))
    out: list[float] = []
    for t in range(len(season_wars)):
        if t < pre_arb:
            out.append(league_min)
            continue
        i = t - pre_arb
        frac = arb_fracs[i] if i < len(arb_fracs) else arb_fracs[-1]
        if arb_basis == "prior_season":
            prior_market = markets[t - 1] if t > 0 else markets[t]
            out.append(max(league_min, frac * prior_market))
        else:
            out.append(frac * markets[t])
    return out
''',
    'value_framework._lowtier_anchor_usd': '''
def _lowtier_anchor_usd(fv: float, role: str, eta_years: float = 0.0) -> float:
    cfg = _config()
    a = cfg["lowtier_anchor"]
    val = float(a["anchor_usd_40fv_position"])
    if role == "pitcher":
        val *= float(a.get("pitcher_scale", 1.0))
    anchor_fv = float(a["anchor_fv"])
    if fv < anchor_fv:
        val *= math.exp(-float(a["decay_per_point"]) * (anchor_fv - fv))
    infl = float(cfg.get("dollars_per_war_inflation", 0.0))
    r = float(cfg["discount_rate"])
    val *= ((1.0 + infl) / (1.0 + r)) ** float(eta_years)
    return val
''',
    'value_framework._remaining_path_surplus_usd': '''
def _remaining_path_surplus_usd(season_wars: list[float], start_k: int, super_two: bool) -> float:
    cfg = _config()
    st = cfg["service_time"]
    league_min = float(st["league_min_usd"])
    pre_arb, arb_fracs = _arb_ladder(st, super_two)
    net = (1.0 + float(cfg.get("dollars_per_war_inflation", 0.0))) / (1.0 + float(cfg["discount_rate"]))
    arb_basis = str(st.get("arb_basis", "current_season"))
    markets = [tiered_war_value_usd(w) for w in season_wars]
    total = 0.0
    start_k = int(start_k)
    for k in range(start_k, len(season_wars)):
        market = markets[k]
        if k < pre_arb:
            salary = league_min
        else:
            i = k - pre_arb
            frac = arb_fracs[i] if i < len(arb_fracs) else arb_fracs[-1]
            if arb_basis == "prior_season":
                prior_market = markets[k - 1] if k > 0 else markets[k]
                salary = max(league_min, frac * prior_market)
            else:
                salary = frac * market   # matches _service_path_salaries exactly (no floor)
        total += (market - salary) * (net ** (k - start_k))
    return total
''',
    'value_framework._realized_consumed_usd': '''
def _realized_consumed_usd(consumed_seasons) -> float:
    if not consumed_seasons:
        return 0.0
    flat = _flat_rate_usd()
    r = float(_config()["discount_rate"])
    n = len(consumed_seasons)
    total = 0.0
    for i, s in enumerate(consumed_seasons):
        fwar = float(s.get("fwar", 0.0))
        salary_usd = float(s.get("salary_mm", 0.0)) * 1e6
        if s.get("market_mm") is not None:
            market_usd = float(s["market_mm"]) * 1e6
        else:
            dpw = float(s["dpw_mm"]) * 1e6 if s.get("dpw_mm") is not None else flat
            market_usd = fwar * dpw
        total += (market_usd - salary_usd) * ((1.0 + r) ** (n - 1 - i))   # compound past -> now
    return total
''',
    'value_framework.realized_consumed_seasons': '''
def realized_consumed_seasons(season_wars_by_year, *, salary_by_year=None,
                              super_two: bool = False) -> list[dict]:
    if not season_wars_by_year:
        return []
    if isinstance(season_wars_by_year, dict):
        items = [(y, season_wars_by_year[y]) for y in season_wars_by_year]
    else:
        items = list(season_wars_by_year)
    rows = []
    for y, w in items:
        try:
            yr = int(y)
            war = float(w)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(war):
            continue
        rows.append((yr, war))
    if not rows:
        return []
    rows.sort(key=lambda t: t[0])

    cfg = _config()
    st = cfg["service_time"]
    league_min_mm = float(st["league_min_usd"]) / 1e6
    control_years = int(st["control_years"])
    pre_arb, arb_fracs = _arb_ladder(st, super_two)
    sby = salary_by_year or {}

    arb_basis = str(st.get("arb_basis", "current_season"))
    markets_mm = [tiered_war_value_usd(w) / 1e6 for _, w in rows]   # $M market, 0 for war<=0
    consumed = []
    for t, (yr, war) in enumerate(rows):
        market_mm = markets_mm[t]
        actual = sby.get(yr, sby.get(str(yr)))
        if actual is not None and float(actual) > 0:
            salary_mm = float(actual) / 1e6
        elif t < pre_arb:
            salary_mm = league_min_mm
        elif t < control_years:
            i = t - pre_arb
            frac = arb_fracs[i] if i < len(arb_fracs) else arb_fracs[-1]
            base_mkt = markets_mm[t - 1] if (arb_basis == "prior_season" and t > 0) else market_mm
            salary_mm = max(league_min_mm, frac * base_mkt)
        else:                                                  # post-control: paid ~fair market
            salary_mm = max(league_min_mm, market_mm)
        consumed.append({"fwar": war, "salary_mm": round(salary_mm, 4),
                         "market_mm": round(market_mm, 4),
                         "dpw_mm": round(dollars_per_war(war), 6), "year": yr})
    return consumed
''',
    'proj_export._season_value_usd': '''
def _season_value_usd(war: float, t: int, dpw_level: float) -> float:
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    infl = float(vf._config().get("dollars_per_war_inflation", 0.05))
    return vf.tiered_war_value_usd(war) * (dpw_level / base_flat) * ((1 + infl) ** t)
''',
    'proj_export._ros_surplus_usd': '''
def _ros_surplus_usd(war_now: float, cur_sal: float, ros_frac: float,
                     dpw_level: float) -> float:
    return float(ros_frac) * (_season_value_usd(float(war_now), 0, dpw_level)
                              - float(cur_sal))
''',
    'fa_market.rational_value_usd': '''
def rational_value_usd(war_by_year: list[float], class_year: int,
                       dpw_usd: float, infl: float | None = None) -> int:
    from value_framework import tiered_war_value_usd
    r = _discount_rate()
    infl = _dpw_inflation() if infl is None else float(infl)
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    total = 0.0
    for t, w in enumerate(war_by_year):
        total += (tiered_war_value_usd(w) * level * ((1 + infl) ** t)) / ((1 + r) ** t)
    return int(total)
''',
    'fa_market.deferral_npv_usd': '''
def deferral_npv_usd(schedule: list[dict] | None, guarantee_usd: int) -> dict:
    r = _discount_rate()
    if not schedule:
        return {"sticker_usd": guarantee_usd, "npv_usd": guarantee_usd,
                "method": "no_deferral_schedule_on_file"}
    npv = sum(row["amount_usd"] / ((1 + r) ** row["year_offset"]) for row in schedule)
    return {"sticker_usd": guarantee_usd, "npv_usd": int(npv), "method": "schedule_npv"}
''',
    'fa_mc.expected_tier_value_usd': '''
def expected_tier_value_usd(point_path, p10_path, p90_path, years: int,
                            class_year: int, dpw_usd: float,
                            infl: float, discount: float,
                            taus=QUAD_TAUS) -> int:
    from value_framework import _config as _vf_config
    from value_framework import tiered_war_value_usd
    level = dpw_usd / float(_vf_config()["dollars_per_war"]["flat"])
    total = 0.0
    n = len(taus)
    for t in range(max(1, int(years))):
        pt = float(point_path[t]) if t < len(point_path) else 0.0
        lo = float(p10_path[t]) if p10_path and t < len(p10_path) else pt
        hi = float(p90_path[t]) if p90_path and t < len(p90_path) else pt
        acc = 0.0
        for u in taus:
            w = two_piece_quantile(pt, lo, hi, u)
            acc += tiered_war_value_usd(w)
        season = (acc / n) * level * ((1 + infl) ** t)
        total += season / ((1 + discount) ** t)
    return int(total)
''',
}


def _legacy(module, name):
    ns = dict(vars(module))
    exec(LEGACY[f"{module.__name__}.{name}"], ns)
    return ns[name]


def _wars(seed, n=7):
    rng = random.Random(seed)
    return [round(rng.uniform(-0.5, 5.5), 3) for _ in range(n)]


def test_the_switch_is_off_and_no_block_is_written():
    assert vf.SERVE_DPW_PATH is False and fm.WRITE_DPW_PATH_BLOCK is False
    assert vf.dpw_path_on() is False and vf.dpw_path_active() is False


@pytest.mark.parametrize("seed", range(6))
def test_engine_paths_equal_their_pre_build_bodies_off(seed):
    wars = _wars(seed)
    sp = _legacy(vf, "_service_path_surplus_usd")
    rem = _legacy(vf, "_remaining_path_surplus_usd")
    for super_two in (False, True):
        for eta in (0.0, 1.25, 3.5):
            assert vf._service_path_surplus_usd(wars, super_two, eta) == sp(wars, super_two, eta)
            assert vf._service_path_surplus_usd(wars, super_two, eta, eta_origin=2026) == \
                sp(wars, super_two, eta)
        for k in (0, 2, 5):
            assert vf._remaining_path_surplus_usd(wars, k, super_two) == rem(wars, k, super_two)
    anchor = _legacy(vf, "_lowtier_anchor_usd")
    for fv in (35.0, 38.5, 40.0, 42.0):
        for role in ("hitter", "pitcher"):
            assert vf._lowtier_anchor_usd(fv, role, 2.0) == anchor(fv, role, 2.0)
            assert vf._lowtier_anchor_usd(fv, role, 2.0, 2027) == anchor(fv, role, 2.0)


def test_the_realized_leg_equals_its_pre_build_body_off():
    rcs = _legacy(vf, "realized_consumed_seasons")
    rcu = _legacy(vf, "_realized_consumed_usd")
    by_year = {2021: 0.4, 2022: 2.1, 2023: 3.3, 2024: 2.8, 2025: 4.0, 2026: 1.9, 2027: 2.2, 2028: 2.5}
    for sby in (None, {2024: 4_500_000}):
        for s2 in (False, True):
            a = vf.realized_consumed_seasons(by_year, salary_by_year=sby, super_two=s2)
            b = rcs(by_year, salary_by_year=sby, super_two=s2)
            assert a == b
            assert vf._realized_consumed_usd(a) == rcu(b)


@pytest.mark.parametrize("seed", range(4))
def test_veteran_and_fa_pricing_equal_their_pre_build_bodies_off(seed):
    wars = _wars(seed, 6)
    sv = _legacy(proj_export, "_season_value_usd")
    ros = _legacy(proj_export, "_ros_surplus_usd")
    for t, w in enumerate(wars):
        assert proj_export._season_value_usd(w, t, 17_143_641.0) == sv(w, t, 17_143_641.0)
    assert proj_export._ros_surplus_usd(wars[0], 9_000_000, 0.3, 17e6) == \
        ros(wars[0], 9_000_000, 0.3, 17e6)
    rv = _legacy(fm, "rational_value_usd")
    for infl in (None, 0.0, 0.0416):
        assert fm.rational_value_usd(wars, 2027, 17.14e6, infl) == rv(wars, 2027, 17.14e6, infl)
    p10 = [max(0.0, w - 1.0) for w in wars]
    p90 = [w + 1.2 for w in wars]
    et = _legacy(fa_mc, "expected_tier_value_usd")
    assert fa_mc.expected_tier_value_usd(wars, p10, p90, 5, 2027, 17.14e6, 0.04, 0.07) == \
        et(wars, p10, p90, 5, 2027, 17.14e6, 0.04, 0.07)
    dn = _legacy(fm, "deferral_npv_usd")
    sched = [{"year_offset": t, "amount_usd": 2_000_000} for t in range(10)]
    assert fm.deferral_npv_usd(sched, 20_000_000) == dn(sched, 20_000_000)
    assert fm.deferral_npv_usd(None, 20_000_000) == dn(None, 20_000_000)


def test_the_public_engine_is_unchanged_by_an_origin_off():
    for fv in (38.0, 45.0, 55.0, 62.0):
        base = vf.surplus_value_mm(fv, False, "SS", age=21, eta_years=2.5)
        assert vf.surplus_value_mm(fv, False, "SS", age=21, eta_years=2.5, eta_origin=2026) == base
        assert vf.surplus_value_mm(fv, False, "SS", age=21, eta_years=2.5, eta_origin=2031) == base
        d0 = vf.sv_distribution(fv, True, "SP", age=22, eta_years=1.0, draws=400)
        d1 = vf.sv_distribution(fv, True, "SP", age=22, eta_years=1.0, draws=400, eta_origin=2027)
        assert d0 == d1
    assert "pricing_basis_id" not in vf.calibration_stamp()
    assert "dpw_path" not in vf.build_snapshot()


def test_the_bucket_cache_is_keyed_on_the_basis(tmp_path):
    off = vf._bucket_sv_usd("hitter", False, None, 1.0)
    with kit.unified(tmp_path):
        on = vf._bucket_sv_usd("hitter", False, None, 1.0, 1.0, 2026)
        assert on != off
    assert vf._bucket_sv_usd("hitter", False, None, 1.0) == off


def test_the_environment_can_only_force_it_off(monkeypatch, tmp_path):
    monkeypatch.setenv("EEPHUS_SERVE_DPW_PATH", "1")
    assert vf.dpw_path_on() is False                  # no environment value turns it ON
    monkeypatch.setattr(vf, "SERVE_DPW_PATH", True)
    assert vf.dpw_path_on() is True                   # only the committed constant does
    monkeypatch.setenv("EEPHUS_SERVE_DPW_PATH", "0")
    assert vf.dpw_path_on() is False                  # and the environment forces it off
    with kit.unified(tmp_path):
        assert vf.dpw_path_on() is False and vf.dpw_path_active() is False
    monkeypatch.delenv("EEPHUS_SERVE_DPW_PATH")
    src = Path(vf.__file__).read_text(encoding="utf-8")
    assert src.count("return bool(SERVE_DPW_PATH)") == 1


def test_dpw_path_forced_is_called_only_by_the_allowlist():
    allow = {"dpw_testkit.py", "dpw_path_gate.py", "dpw_blast_radius.py"}
    callers = []
    for p in list(ROOT.glob("*.py")) + list((ROOT / "tools").glob("*.py")):
        if p.name.startswith("test_") or p.name in allow or p.name == "value_framework.py":
            continue
        if "dpw_path_forced(" in p.read_text(encoding="utf-8", errors="replace"):
            callers.append(p.name)
    assert callers == [], callers


def _levers():
    return {"base": vf.discount_base_season(legacy_base=2026.0), "rate": vf.nominal_rate(),
            "g": vf.g_ref(), "min": vf.league_min_for(2032, legacy=760_000.0),
            "arb": vf.arb_index_scale(2032), "tm": vf.dpw_option("trade_machine"),
            "level": vf.price_level(2027)}


LEVER_OF = {"U1a": {"base"}, "U1b": {"rate", "g", "min", "arb"}, "U1c": {"tm"}, "U2": {"level"}}


def test_each_stage_moves_only_its_own_lever(tmp_path):
    with kit.unified(tmp_path, stages=()):
        none = _levers()
    assert none["rate"] == float(vf._config()["discount_rate"]) and none["g"] == 0.0
    assert none["tm"] == "keep" and none["base"] == 2026.0
    for stage, levers in LEVER_OF.items():
        with kit.unified(tmp_path, stages=(stage,), level_n=15.0e6):
            got = _levers()
        moved = {k for k in got if got[k] != none[k]}
        assert moved == levers, (stage, moved)
    with pytest.raises(ValueError):
        with vf.dpw_path_forced(True, stages=("U9",)):
            pass
