# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Versioned prospect-valuation SETS (Phase 1 of the Clemens-2026 recalibration).

A valuation set is a FIRST-CLASS, versioned config artifact under
``config/valuation_sets/<id>.yaml``. Each set carries:

  * ``tiers``  -- the published FV x role tier table (surplus_musd, ctrl_war,
                  and, where the framework publishes it, star_odds). This is a
                  CALIBRATION TARGET and a FALLBACK PRIOR, never a per-player
                  override: model mode prices players through the career-path
                  mixture engine and only reconciles its tier AGGREGATES to this
                  table; table mode prices players directly at these values.
  * ``params`` -- the global valuation parameters the kernel/salary/discount
                  layers consume (win-cost tiers, arbitration schedule, discount,
                  control-year convention, star definition, residence time).
  * ``meta``   -- provenance (source URLs, retrieval date, win-cost basis,
                  caveats).

Two sets ship:

  * ``prospx_current`` -- the LEGACY production engine (the BASE-IDENTITY set),
    captured so table mode reproduces the pre-flip live board and the legacy
    pipeline stays reproducible. NOTE on naming: the prompt called this
    ``edwards_2019``, but the live anchors are NOT raw Edwards 2019 -- they were
    empirically re-anchored (v47) to realized 2017-2020 outcomes (see
    docs/surplus-recalibration.md). We name it honestly and keep ``edwards_2019``
    as an alias. Its ``params`` MIRROR value_framework_config.yaml; because it is
    byte-identical to the base config its overlay is a no-op (selecting it re-
    prices to the exact legacy engine).
  * ``clemens_2026`` -- the FanGraphs / Ben Clemens (2026) published framework,
    fetched from the three source posts on 2026-07-03 and checksum-validated
    against the values in the recalibration spec. As of the 2026-07 flip this is
    the PRODUCTION DEFAULT (MODEL mode): its ``params`` deep-merge onto the base
    config so the career-path engine reprices per player under the FanGraphs
    market conventions.

Units: dollars in MILLIONS of nominal 2026 USD (``*_musd``); WAR per the field.

The loader REFUSES to run on a malformed set: it rejects nulls in required
fields and rejects any set whose published tiers fail the embedded checksum
block. Nothing here imports value_framework, so it stays a leaf dependency.
"""
from __future__ import annotations

import functools
from pathlib import Path

_HERE = Path(__file__).resolve().parent
SETS_DIR = _HERE / "config" / "valuation_sets"

# The PRODUCTION default set the engine boots under (flipped 2026-07 to
# clemens_2026; MODEL mode). prospx_current is the BASE-IDENTITY set -- byte-
# identical to value_framework_config.yaml, whose overlay is a no-op (see
# value_framework._BASE_IDENTITY_SET / _apply_valuation_overlay).
DEFAULT_SET = "clemens_2026"
BASE_IDENTITY_SET = "prospx_current"
# Historical / prompt-facing aliases -> canonical set id.
_ALIASES = {"edwards_2019": "prospx_current"}

# Tier grade labels and their numeric FV-axis values (the "+" grades sit on the
# half-tier axis, matching value_framework_config.yaml plus_grade_axis).
_TIER_AXIS = {
    "35+": 37.5, "40": 40.0, "40+": 42.5, "45": 45.0, "45+": 47.5,
    "50": 50.0, "55": 55.0, "60": 60.0, "65": 65.0, "70": 70.0,
}
_ROLES = ("hitter", "pitcher")


class ValuationSetError(ValueError):
    """A valuation set is missing, malformed, carries a null in a required field,
    or fails its checksum block. Raised at load so a bad set fails LOUDLY."""


# =============================================================================
# Checksums -- the load-bearing tier values verified against the three FanGraphs
# source posts on 2026-07-03 (see the recalibration spec). A fetched/edited set
# that drifts from these beyond rounding is an EXTRACTION ERROR: refuse to load.
# surplus_musd tolerance = 0.05 ($M); star_odds tolerance = 0.001. A (lo, hi)
# value is an inclusive plausible RANGE rather than a point.
# =============================================================================
_CHECKSUMS = {
    "clemens_2026": {
        ("hitter", "50"): {"surplus_musd": 45.0, "star_odds": 0.135},
        ("pitcher", "50"): {"surplus_musd": 33.5, "star_odds": 0.070},
        ("hitter", "45"): {"surplus_musd": 14.5},
        ("hitter", "45+"): {"surplus_musd": 18.5},
        ("hitter", "40"): {"surplus_musd": 5.5},
        ("hitter", "70"): {"surplus_musd": (150.0, 200.0)},  # plausible range
    },
}
_SURPLUS_TOL = 0.05
_STAR_TOL = 0.001


def _canon(set_id: str) -> str:
    return _ALIASES.get(set_id, set_id)


def available() -> list[str]:
    """All shippable set ids (canonical), sorted."""
    if not SETS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SETS_DIR.glob("*.yaml"))


@functools.lru_cache(maxsize=8)
def load(set_id: str) -> dict:
    """Parse + validate a valuation set by id (alias-resolved). Cached. Raises
    ValuationSetError on a missing file, a null in a required field, or a
    checksum failure."""
    import yaml  # pyyaml; only needed to read the set

    cid = _canon(set_id)
    path = SETS_DIR / f"{cid}.yaml"
    if not path.exists():
        raise ValuationSetError(
            f"unknown valuation set '{set_id}'"
            f"{'' if cid == set_id else f' (alias of {cid})'}; "
            f"available: {available()}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    _validate(data, cid)
    return data


def _validate(data: dict, cid: str) -> None:
    if not isinstance(data, dict):
        raise ValuationSetError(f"{cid}: did not parse to a mapping")
    if data.get("id") != cid:
        raise ValuationSetError(
            f"{cid}: 'id' field is {data.get('id')!r}, expected {cid!r}")
    tiers = data.get("tiers")
    if not isinstance(tiers, dict):
        raise ValuationSetError(f"{cid}: missing 'tiers' mapping")
    for role in _ROLES:
        rt = tiers.get(role)
        if not isinstance(rt, dict) or not rt:
            raise ValuationSetError(f"{cid}: tiers.{role} missing or empty")
        for label, row in rt.items():
            if label not in _TIER_AXIS:
                raise ValuationSetError(
                    f"{cid}: tiers.{role}['{label}'] is not a known tier "
                    f"({sorted(_TIER_AXIS)})")
            if not isinstance(row, dict):
                raise ValuationSetError(f"{cid}: tiers.{role}['{label}'] not a mapping")
            # Required non-null fields. star_odds is OPTIONAL (a Clemens-framework
            # output); if PRESENT it must be non-null and a probability. A present
            # null in ANY field is rejected -- "existing data only, nulls refuse".
            for req in ("surplus_musd", "ctrl_war"):
                if row.get(req) is None:
                    raise ValuationSetError(
                        f"{cid}: tiers.{role}['{label}'].{req} is null/missing")
            for k, v in row.items():
                if v is None:
                    raise ValuationSetError(
                        f"{cid}: tiers.{role}['{label}'].{k} is null")
            so = row.get("star_odds")
            if so is not None and not (0.0 <= float(so) <= 1.0):
                raise ValuationSetError(
                    f"{cid}: tiers.{role}['{label}'].star_odds={so} not in [0,1]")
    _validate_checksums(data, cid)


def _validate_checksums(data: dict, cid: str) -> None:
    checks = _CHECKSUMS.get(cid)
    if not checks:
        return
    tiers = data["tiers"]
    for (role, label), want in checks.items():
        row = tiers.get(role, {}).get(label)
        if row is None:
            raise ValuationSetError(
                f"{cid}: checksum tier {role}/{label} is ABSENT from the set")
        got_s = float(row["surplus_musd"])
        exp_s = want["surplus_musd"]
        if isinstance(exp_s, tuple):
            lo, hi = exp_s
            if not (lo - _SURPLUS_TOL <= got_s <= hi + _SURPLUS_TOL):
                raise ValuationSetError(
                    f"{cid}: CHECKSUM FAIL {role}/{label} surplus_musd={got_s} "
                    f"outside range [{lo}, {hi}]")
        elif abs(got_s - float(exp_s)) > _SURPLUS_TOL:
            raise ValuationSetError(
                f"{cid}: CHECKSUM FAIL {role}/{label} surplus_musd={got_s} "
                f"!= {exp_s} (tol {_SURPLUS_TOL})")
        if "star_odds" in want:
            got_o = row.get("star_odds")
            if got_o is None or abs(float(got_o) - float(want["star_odds"])) > _STAR_TOL:
                raise ValuationSetError(
                    f"{cid}: CHECKSUM FAIL {role}/{label} star_odds={got_o} "
                    f"!= {want['star_odds']} (tol {_STAR_TOL})")


# =============================================================================
# Table mode -- price a player DIRECTLY at their tier value (exact replication of
# the published framework; the fallback + display option). Monotone piecewise
# linear in FV over the tier grid, clamped outside the grid.
# =============================================================================
def _role_grid(data: dict, role: str, field: str) -> list[tuple[float, float]]:
    rt = data["tiers"][role]
    pts = [(_TIER_AXIS[label], float(row[field]))
           for label, row in rt.items() if row.get(field) is not None]
    return sorted(pts)


def _interp(grid: list[tuple[float, float]], fv: float) -> float | None:
    if not grid:
        return None
    if fv <= grid[0][0]:
        return grid[0][1]
    if fv >= grid[-1][0]:
        return grid[-1][1]
    for (x0, y0), (x1, y1) in zip(grid, grid[1:]):
        if x0 <= fv <= x1:
            if x1 == x0:
                return y1
            t = (fv - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return grid[-1][1]


def table_value_musd(set_id: str, fv: float, is_pitcher: bool) -> float | None:
    """Table-mode surplus ($M) for a player at continuous FV and role."""
    if fv is None:
        return None
    data = load(set_id)
    role = "pitcher" if is_pitcher else "hitter"
    return _interp(_role_grid(data, role, "surplus_musd"), float(fv))


def table_star_odds(set_id: str, fv: float, is_pitcher: bool) -> float | None:
    """Table-mode star odds for a player at continuous FV and role (None if the
    set does not publish star odds)."""
    if fv is None:
        return None
    data = load(set_id)
    role = "pitcher" if is_pitcher else "hitter"
    grid = _role_grid(data, role, "star_odds")
    return _interp(grid, float(fv)) if grid else None


def tier_table(set_id: str, role: str) -> dict[str, dict]:
    """The raw published tier rows for a role (label -> {surplus_musd, ...})."""
    return dict(load(set_id)["tiers"][role])


# =============================================================================
# Engine overlay -- translate a set's human ``params`` block into a partial
# value_framework config dict for deep-merge onto the base config. Consumed by
# value_framework._apply_valuation_overlay for NON-default sets only (the default
# set's params are documentation; the base config stays authoritative).
# =============================================================================
def discount_form_literal(set_id: str) -> str:
    """The set's literal discount.form string (clemens_2026: net_7_flat). Read-only."""
    disc = (load(set_id).get("params") or {}).get("discount")
    if not disc:
        raise ValuationSetError(f"{set_id}: no discount block")
    return str(disc.get("form", "net_flat"))


def discount_form(set_id: str) -> str:
    """The set's discount FORM for the unified $/WAR path (VAL_5, I7): the literal
    strings net_7_flat and net_flat both map to net_flat, rate_minus_growth is
    returned as is, and any other string raises. Read-only: the resolved config
    dict is not changed."""
    form = discount_form_literal(set_id)
    if form in ("net_7_flat", "net_flat"):
        return "net_flat"
    if form == "rate_minus_growth":
        return form
    raise ValuationSetError(f"{set_id}: unknown discount.form '{form}'")


def engine_params(set_id: str) -> dict:
    """Partial value_framework config overlay for the set's ``params`` block.
    Returns {} when the set carries no params. Units: musd -> usd here."""
    data = load(set_id)
    p = data.get("params") or {}
    out: dict = {}

    wc = p.get("win_cost")
    if wc:
        dpw: dict = {}
        if wc.get("flat_musd") is not None:
            dpw["flat"] = float(wc["flat_musd"]) * 1e6
        if wc.get("breakpoints") is not None or wc.get("rates_musd") is not None:
            tiered: dict = {}
            if wc.get("breakpoints") is not None:
                tiered["breakpoints"] = [float(b) for b in wc["breakpoints"]]
            if wc.get("rates_musd") is not None:
                tiered["rates"] = {k: float(v) * 1e6 for k, v in wc["rates_musd"].items()}
            dpw["tiered"] = tiered
        if wc.get("level") == "fa_winter":
            # VAL_1 (owner decision FP2-1, 2026-09-25): the published tier SHAPE,
            # rescaled to the free-agent winter level of the one written series
            # (value_framework._apply_fa_winter_level). trailing_years is unused on
            # this method and kept only so the block validates.
            dpw["fa_implied"] = {"enabled": True, "trailing_years": 3,
                                 "method": "fa_winter_level"}
        elif wc.get("disable_fa_implied"):
            # Faithful replication of the published framework uses the FG cost-of-win
            # directly, NOT our FA-implied rescale. Keep trailing_years so the block
            # still validates.
            dpw["fa_implied"] = {"enabled": False, "trailing_years": 3}
        if wc.get("kernel_mode") is not None:
            dpw["kernel_mode"] = str(wc["kernel_mode"])
        if dpw:
            out["dollars_per_war"] = dpw

    disc = p.get("discount")
    if disc:
        # The prompt's rule: apply EXACTLY ONE of {net 7% with flat win cost} or
        # {10% with 3% win-cost growth}. We use the exact net-7%-flat branch:
        # engine net factor = (1+infl)/(1+rate); infl=0, rate=net_rate -> 1/1.07.
        form = str(disc.get("form", "net_flat"))
        if form in ("net_7_flat", "net_flat"):
            out["discount_rate"] = float(disc["net_rate"])
            out["dollars_per_war_inflation"] = 0.0
        elif form == "rate_minus_growth":
            out["discount_rate"] = float(disc["rate"])
            out["dollars_per_war_inflation"] = float(disc["growth"])
        else:
            raise ValuationSetError(f"{set_id}: unknown discount.form '{form}'")

    arb = p.get("arbitration")
    ctrl = p.get("control")
    st: dict = {}
    if arb:
        am: dict = {}
        if arb.get("schedule") is not None:
            am["fractions_of_fa_value"] = [float(x) for x in arb["schedule"]]
        if am:
            st["arb_model"] = am
        if arb.get("pre_arb_years") is not None:
            st["pre_arb_years"] = int(arb["pre_arb_years"])
        if arb.get("basis") is not None:
            # New key; consumed by the Phase-3 salary path (prior_season vs current).
            st["arb_basis"] = str(arb["basis"])
    if ctrl and ctrl.get("years") is not None:
        st["control_years"] = int(ctrl["years"])
    if ctrl and ctrl.get("basis") is not None:
        st["control_basis"] = str(ctrl["basis"])
    if st:
        out["service_time"] = st

    # Star definition + residence: new engine keys (consumed Phase 4 / Phase 5).
    if p.get("star"):
        out["star_definition"] = dict(p["star"])
    if p.get("residence"):
        out["residence"] = dict(p["residence"])

    return out


def implied_pick_surplus(fv: float | None, is_pitcher: bool,
                         bonus_usd: float | None = None,
                         slot_usd: float | None = None,
                         set_id: str = "clemens_2026") -> dict | None:
    """Implied draft-pick surplus: the valuation set's TABLE value for the drafted
    player's FV and role, minus the pick's cost. Cost is the ACTUAL signing bonus
    when known, otherwise the EXPECTED slot value. Returns a dict:

        {surplus_usd, cost_usd, basis, tier_value_usd}

    basis is 'actual_bonus' (a real signing bonus, including over-slot deals) or
    'expected_slot' (pre-signing, priced at slot). Returns None when FV is missing
    or when NO real cost is available (never guesses a bonus). Units: USD."""
    if fv is None:
        return None
    tv = table_value_musd(set_id, float(fv), bool(is_pitcher))
    if tv is None:
        return None
    if bonus_usd is not None:
        cost, basis = float(bonus_usd), "actual_bonus"
    elif slot_usd is not None:
        cost, basis = float(slot_usd), "expected_slot"
    else:
        return None   # no real cost data -> no guess (per the recon gate)
    tier_usd = float(tv) * 1e6
    return {"surplus_usd": round(tier_usd - cost, 0), "cost_usd": round(cost, 0),
            "basis": basis, "tier_value_usd": round(tier_usd, 0)}


def reset_cache() -> None:
    load.cache_clear()
