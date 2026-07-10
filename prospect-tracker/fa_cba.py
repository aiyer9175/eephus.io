# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rule-versioned CBA logic for the MLB Free Agency module.

Every QO / CBT / pick-forfeiture computation in the module resolves its
rules through this file, and this file resolves them from DATED RECORDS in
``data/cba_rules.json`` + ``data/qo_history.json`` — never from hardcoded
constants and never from model memory. When the post-2026 CBA lands, its
thresholds and matrices slot in as new records; zero logic rewrites here.

The 2022 CBA expires 2026-12-01 — mid-market for the 2026-27 class. Any
rule resolved past its regime's ``effective_to`` is returned with
``carry_forward=True``; consumers MUST surface that flag (the UI renders
it as the CBA-uncertainty banner on every 2026-27 contract figure).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CBA_RULES_PATH = DATA_DIR / "cba_rules.json"
QO_HISTORY_PATH = DATA_DIR / "qo_history.json"

# Payor tiers used by the QO compensation matrix. Mirrors the rule file's
# keys exactly — callers pass one of these strings.
PAYOR_CBT = "cbt_payor"
PAYOR_REVENUE_SHARING = "revenue_sharing_recipient"
PAYOR_OTHER = "other"


@lru_cache(maxsize=1)
def _rules() -> dict:
    return json.loads(CBA_RULES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _qo_history() -> dict:
    return json.loads(QO_HISTORY_PATH.read_text(encoding="utf-8"))


def reload() -> None:
    """Drop the cached rule files (tests + post-edit refresh)."""
    _rules.cache_clear()
    _qo_history.cache_clear()


def regime_as_of(d: date | str) -> dict:
    """The CBA regime record covering date ``d``. Past the last regime's
    ``effective_to`` (i.e. after the 2022 CBA expires) the LAST regime is
    returned with ``carry_forward=True`` stamped on a copy — the honest
    "rules unknown, carrying forward" answer the UI must disclose."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    regimes = sorted(_rules()["cba_regimes"], key=lambda r: r["effective_from"])
    for r in regimes:
        if date.fromisoformat(r["effective_from"]) <= d <= date.fromisoformat(r["effective_to"]):
            return dict(r, carry_forward=False)
    last = regimes[-1]
    if d > date.fromisoformat(last["effective_to"]):
        return dict(last, carry_forward=True)
    # Before the first encoded regime — explicit refusal beats a wrong answer.
    raise LookupError(f"no CBA regime encoded for {d} (earliest is {regimes[0]['effective_from']})")


def cbt_threshold(season: int) -> dict:
    """{threshold_usd, carry_forward, regime, verify_status} for a season.
    Unknown future seasons resolve to the latest encoded threshold with
    carry_forward=True (never silently invented)."""
    rows = _rules()["cbt_thresholds"]
    by_season = {r["season"]: r for r in rows}
    if season in by_season:
        r = by_season[season]
        return {
            "threshold_usd": r["threshold_usd"],
            "carry_forward": bool(r.get("carry_forward", False)),
            "regime": r.get("regime"),
            "verify_status": r.get("verify_status", "curated-unverified"),
        }
    latest = max(rows, key=lambda r: r["season"])
    if season > latest["season"]:
        return {
            "threshold_usd": latest["threshold_usd"],
            "carry_forward": True,
            "regime": "post_cba_2022_unknown",
            "verify_status": "explicitly-unknown",
        }
    raise LookupError(f"no CBT threshold encoded for season {season}")


def cbt_surcharge_tiers() -> list[int]:
    """Dollar offsets above the base threshold where surcharge tiers begin."""
    return list(_rules()["cbt_surcharge_tiers_usd"]["tiers_above_threshold"])


def cbt_tax_rates() -> dict:
    return dict(_rules()["cbt_tax_rates"])


def qo_value(class_year: int) -> dict | None:
    """The qualifying-offer value for the winter whose contracts cover
    ``class_year`` (winter 2023-24 -> class_year 2024). None when the
    winter hasn't announced a value yet (e.g. 2027 pre-announcement) —
    callers render an explicit unknown, never an invented number."""
    for r in _rules()["qo_values"]:
        if r["class_year"] == class_year:
            return dict(r)
    return None


def qo_compensation(as_of: date | str) -> dict:
    """The full QO compensation record (signing-team forfeiture matrix +
    losing-team compensation) in force at ``as_of``, with carry_forward
    stamped when resolved past the encoded regime."""
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of[:10])
    recs = _rules()["qo_compensation"]
    for r in recs:
        if date.fromisoformat(r["effective_from"]) <= as_of <= date.fromisoformat(r["effective_to"]):
            return dict(r, carry_forward=False)
    last = max(recs, key=lambda r: r["effective_to"])
    if as_of > date.fromisoformat(last["effective_to"]):
        return dict(last, carry_forward=True)
    raise LookupError(f"no QO compensation rules encoded for {as_of}")


def pick_forfeiture(payor_tier: str, as_of: date | str) -> dict:
    """What a signing team forfeits for signing a QO-attached free agent:
    {picks: [...], intl_pool_usd, carry_forward}. ``payor_tier`` is one of
    PAYOR_CBT / PAYOR_REVENUE_SHARING / PAYOR_OTHER."""
    comp = qo_compensation(as_of)
    matrix = comp["signing_team_forfeits"]
    if payor_tier not in matrix:
        raise KeyError(f"unknown payor tier {payor_tier!r}; expected one of {sorted(matrix)}")
    return dict(matrix[payor_tier], carry_forward=comp["carry_forward"])


def qo_acceptances(class_year: int | None = None) -> list[dict]:
    rows = _qo_history()["acceptances"]
    return [dict(r) for r in rows if class_year is None or r["class_year"] == class_year]


def qo_offered_count(class_year: int) -> int | None:
    for r in _qo_history()["offered_counts_by_winter"]:
        if r["class_year"] == class_year:
            return int(r["offered"])
    return None


def unverified_records() -> list[str]:
    """Every record still flagged curated-unverified — surfaced at the
    Stage-1 checkpoint so the owner can spot-check the curation."""
    out: list[str] = []
    rules = _rules()
    for key in ("cba_regimes", "cbt_thresholds", "qo_values", "qo_compensation"):
        for r in rules.get(key, []):
            if r.get("verify_status") == "curated-unverified":
                label = r.get("regime") or r.get("season") or r.get("winter") or key
                out.append(f"{key}:{label}")
    for r in _qo_history().get("acceptances", []):
        if r.get("verify_status") == "curated-unverified":
            out.append(f"qo_acceptance:{r['class_year']}:{r['player_name']}")
    return out
