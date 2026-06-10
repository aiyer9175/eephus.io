# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Free-agent class construction + the retrospective contract ledger.

A class for offseason ``class_year`` (2027 = the 2026-27 winter) is DERIVED
from ingested Spotrac rows — never hand-listed, never from model memory:

  LOCKED            fa_type == ufa: contract expires, no decision pending.
  PENDING_OPTION    player/club/mutual/conditional options + opt-outs:
                    membership is probabilistic until the option resolves,
                    and the row carries a modeled exercise probability.
                    v1 is a DOCUMENTED logistic heuristic (fa_config.yaml)
                    on option price vs a crude rational AAV — flagged in
                    the payload as heuristic, replaced by a learned model
                    in v2.
  QO flags          arrive from the ingested rows themselves (Spotrac marks
                    QO inline on signed rows); acceptances from the curated
                    qo_history.json. Pre-offer winters carry qo=None — the
                    UI says "undetermined", it never guesses.

Reconciliation guardrail: the parsed row count is checked against the
page's own advertised count (the "Player (229)" header) — the constructed
class must cover the authoritative tracker, and shortfalls are reported,
not papered over.

The retrospective ledger prices every completed historical signing:
realized WAR delivered over the contract's elapsed seasons × per-season
$/WAR vs money paid → realized surplus to date. v1 backcasts the
value_framework rate by its own configured escalation until the Stage-3
market model estimates per-winter $/WAR from the corpus itself
(ledger.backcast_mode in fa_config.yaml — documented, not hidden).
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

import fa_cba
import fa_sources
from value_framework import dollars_per_war_flat, _config as _vf_config

log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "fa_config.yaml"


@lru_cache(maxsize=1)
def get_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Option-exercise heuristic (v1 — documented simplification)
# --------------------------------------------------------------------------- #

def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _flat_dpw_usd() -> float:
    """The framework's flat $/WAR in DOLLARS (the public helper returns $M)."""
    return dollars_per_war_flat() * 1_000_000.0


def _crude_rational_aav(row: dict) -> float | None:
    """The roughest defensible market anchor for the option decision, in
    preference order: Spotrac's own market-value AAV → prev WAR × the
    framework's flat $/WAR → the player's current AAV (his last market
    print). None only when all three are absent — the caller then reports
    an explicitly-unknown probability rather than guessing."""
    if row.get("market_value_aav_usd"):
        return float(row["market_value_aav_usd"])
    if row.get("prev_war") is not None:
        return max(0.0, float(row["prev_war"])) * _flat_dpw_usd()
    if row.get("prev_aav_usd"):
        return float(row["prev_aav_usd"])
    return None


def exercise_probability(row: dict) -> dict:
    """P(the player ENTERS the class) for an option-pending row, with the
    method labeled so the UI can disclose it.

    opt_out / player_option: the player walks when the market beats the
    option — P(enter) = logistic((rational − option_price)/scale).
    club_option / conditional_club: the CLUB declines when the option
    out-prices the player — P(enter) = logistic((option − rational)/scale).
    mutual_option: both sides almost never exercise; explicit prior.
    """
    cfg = get_config()["class_construction"]
    fa_type = row.get("fa_type")
    if fa_type == "ufa":
        return {"enter_prob": 1.0, "method": "locked"}
    price = row.get("option_price_usd")
    rational = _crude_rational_aav(row)
    if fa_type == "mutual_option":
        return {"enter_prob": cfg["mutual_option_decline_prob"], "method": "mutual_prior"}
    if fa_type in ("conditional_player_option", "conditional_club_option"):
        return {"enter_prob": cfg["conditional_option_unknown_prob"], "method": "conditional_unknown"}
    if price is None or rational is None:
        return {"enter_prob": None, "method": "insufficient_data"}
    scale = float(cfg["exercise_logistic_scale_usd"])
    if fa_type in ("opt_out", "player_option"):
        p = _logistic((rational - price) / scale)
    elif fa_type in ("club_option",):
        p = _logistic((price - rational) / scale)
    else:
        return {"enter_prob": None, "method": f"unknown_type:{fa_type}"}
    return {"enter_prob": round(p, 3), "method": "heuristic_logistic_v1"}


# --------------------------------------------------------------------------- #
# Class construction
# --------------------------------------------------------------------------- #

def _advertised_count(html_rows: list[dict], page_count: int | None) -> dict:
    """Coverage report vs the page's own advertised player count — the
    reconciliation guardrail (the page IS the authoritative tracker)."""
    parsed = len(html_rows)
    return {
        "parsed": parsed,
        "advertised": page_count,
        "coverage": (parsed / page_count) if page_count else None,
    }


def build_current_class(class_year: int, force: bool = False) -> dict:
    """The constructed (pre-resolution) class for the coming winter.

    Returns {"class_year", "built_at", "players": [...], "reconciliation",
    "qo_note"}. Each player row carries status + enter_prob + the raw
    ingested fields; nothing here is invented."""
    rows = fa_sources.scrape_spotrac_fa_available(class_year, force=force)
    players = []
    for r in rows:
        ep = exercise_probability(r)
        status = "locked" if r["fa_type"] == "ufa" else "pending_option"
        players.append({
            **r,
            "status": status,
            "enter_prob": ep["enter_prob"],
            "enter_prob_method": ep["method"],
            # QO offers for this winter don't exist yet pre-offseason —
            # None means "undetermined", and the UI must say so.
            "qo_offered": None,
            "qo_value_usd": (fa_cba.qo_value(class_year) or {}).get("value_usd"),
        })
    # Advertised count from the page header ("Player (229)") — re-read the
    # cached page so reconciliation uses the same artifact we parsed.
    page_count = None
    try:
        from scrapers import _fetch
        fr = _fetch(f"https://www.spotrac.com/mlb/free-agents/available/_/year/{class_year}",
                    f"spotrac_fa_avail_{class_year}")
        m = re.search(r"Player\s*\((\d+)\)", fr.body or "")
        page_count = int(m.group(1)) if m else None
    except Exception:                                    # noqa: BLE001 — reconciliation is best-effort
        pass
    recon = _advertised_count(players, page_count)
    if recon["coverage"] is not None and recon["coverage"] < 0.99:
        log.warning("fa class %d: parsed %d of %s advertised rows",
                    class_year, recon["parsed"], recon["advertised"])
    return {
        "class_year": class_year,
        "built_at": date.today().isoformat(),
        "players": players,
        "reconciliation": recon,
        "cba_note": fa_cba.regime_as_of(date(class_year - 1, 12, 15)).get("carry_forward", False)
                    and "CBA rules past 2026-12-01 are carried forward — thresholds unknown" or None,
    }


def build_historical_class(class_year: int, force: bool = False) -> dict:
    """One archived winter: signed ledger rows + unsigned remainder, with
    QO acceptances merged from the curated history. Point-in-time fields
    (age, prev team, platform line) come from the class page itself —
    never backfilled from current state."""
    raw = fa_sources.scrape_spotrac_fa_class(class_year, force=force)
    accepted = {r["player_name"] for r in fa_cba.qo_acceptances(class_year)}
    signed = []
    for r in raw["signed"]:
        signed.append({
            **r,
            "qo_accepted": r["player_name"] in accepted,
        })
    return {
        "class_year": class_year,
        "built_at": date.today().isoformat(),
        "signed": signed,
        "unsigned": raw["unsigned"],
        "qo_offered_count": fa_cba.qo_offered_count(class_year),
        "qo_marked_count": sum(1 for r in signed if r["qo"]),
    }


# --------------------------------------------------------------------------- #
# Retrospective ledger
# --------------------------------------------------------------------------- #

_DPW_SERIES_PATH = Path(__file__).parent / "data" / "fa_dpw_series.json"


@lru_cache(maxsize=1)
def _dpw_series() -> dict[int, float]:
    """The per-winter $/WAR series ESTIMATED FROM THE SIGNING CORPUS
    (written by the Stage-3 market model). Empty when not yet generated."""
    try:
        import json as _json
        raw = _json.loads(_DPW_SERIES_PATH.read_text(encoding="utf-8"))
        return {int(k): float(v) for k, v in raw["usd_per_war_by_winter"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def dollars_per_war_for_season(season: int, current_season: int | None = None) -> float:
    """Per-season $/WAR for the retrospective ledger. PRIMARY: the
    per-winter series estimated from the FA-signing corpus itself
    (data/fa_dpw_series.json, Stage-3 market model — the nearest winter's
    rate when the exact season is absent). FALLBACK (documented v1): the
    framework's flat rate de-escalated by its configured inflation."""
    series = _dpw_series()
    if series:
        if season in series:
            return series[season]
        nearest = min(series, key=lambda y: abs(y - season))
        infl = float(_vf_config().get("dollars_per_war_inflation", 0.05))
        return series[nearest] * ((1.0 + infl) ** (season - nearest))
    cur = current_season or date.today().year
    rate_usd = _flat_dpw_usd()
    infl = float(_vf_config().get("dollars_per_war_inflation", 0.05))
    return rate_usd / ((1.0 + infl) ** max(0, cur - season))


def ledger_for_signing(signing: dict, war_seasons: dict[str, float] | None,
                       current_season: int | None = None) -> dict | None:
    """Realized surplus to date for one completed/elapsed signing.

    realized = Σ_{covered, elapsed seasons} WAR(s) × $/WAR(s)
    paid     = guarantee × elapsed/total years   (level annual proration —
               class pages don't expose deferral schedules; documented)
    surplus  = realized − paid

    None for minor-league deals and signings with no elapsed seasons yet.
    Missing WAR for an elapsed season counts as 0 produced — the player
    delivered nothing that season, which is the honest ledger reading —
    but war_seasons=None (player entirely unresolved) returns None rather
    than scoring a ghost.
    """
    if not signing.get("mlb_deal") or not signing.get("years") or not signing.get("guarantee_usd"):
        return None
    if war_seasons is None:
        return None
    cur = current_season or date.today().year
    start = signing["class_year"]
    years = int(signing["years"])
    elapsed = [s for s in range(start, start + years) if s < cur]
    if not elapsed:
        return None
    realized_usd = 0.0
    war_total = 0.0
    for s in elapsed:
        w = float(war_seasons.get(str(s), 0.0) or 0.0)
        war_total += w
        realized_usd += w * dollars_per_war_for_season(s, cur)
    paid_usd = signing["guarantee_usd"] * (len(elapsed) / years)
    return {
        "elapsed_years": len(elapsed),
        "total_years": years,
        "war_to_date": round(war_total, 1),
        "realized_value_usd": int(realized_usd),
        "paid_to_date_usd": int(paid_usd),
        "surplus_to_date_usd": int(realized_usd - paid_usd),
        "complete": len(elapsed) == years,
        "method": "level_proration_backcast_dpw_v1",
    }


def build_ledger(classes: dict[int, dict], war_by_key: dict[str, dict],
                 current_season: int | None = None) -> list[dict]:
    """The ledger across all archived classes. ``war_by_key`` maps
    player_key → career_war payload ({"seasons": {year: bWAR}}) from the
    existing stats.fetch_career_war_bulk machinery — one WAR source
    site-wide. Unresolved players are skipped and counted, not faked."""
    rows: list[dict] = []
    skipped = 0
    for class_year, cls in sorted(classes.items()):
        for s in cls.get("signed", []):
            cw = war_by_key.get(s.get("player_key") or "")
            led = ledger_for_signing(s, (cw or {}).get("seasons"), current_season)
            if led is None:
                if s.get("mlb_deal") and cw is None:
                    skipped += 1
                continue
            rows.append({**s, "ledger": led})
    if skipped:
        log.warning("fa ledger: %d MLB-deal signings skipped (no WAR resolution)", skipped)
    return rows
