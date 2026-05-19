"""
Spotrac international-signings scraper.

The public Stats API doesn't expose international-amateur signing
bonuses, so we go to the source — Spotrac publishes the full IFA
tracker per signing period at:

    https://www.spotrac.com/mlb/international/_/year/{year}

The page is server-rendered HTML with one `<table id="table">` whose
`<tbody>` rows look like:

    <tr>
      <td><a href="…/82038/roki-sasaki">Roki Sasaki</a></td>
      <td>P</td>
      <td>2025</td>
      <td><img src="…/mlb_lad.png"/> LAD</td>
      <td>Japan</td>
      <td>$6,500,000</td>
      <td>80.22%</td>
    </tr>

We parse those rows, normalize the team abbreviation (Spotrac uses MLB
3-letter codes that already match our canonical org codes for the most
part — see `_SPOTRAC_TEAM_OVERRIDES` for the 1-2 outliers), and produce
records suitable for two consumers:

  1. Enriching the per-prospect `acquisitions[].bonus_usd` field for
     IFA-method players in the existing tracker, matched by player_key
     (normalize_key applied to the Spotrac name string).

  2. Aggregating per-org IFA spending totals per year — this captures
     *every* signing, including the org-fillers we never grade, so the
     farm-page "IFA spending vs draft spending" comparison reflects the
     true dollar commitment rather than just the share that bled into
     our prospect set.

Failure modes are explicit: a single empty `<tbody>` returns []
without raising; HTTP non-200 logs a warning and returns []; the
cache lives under `.cache/spotrac_ifa_{year}.html` and survives
re-runs so a flaky upstream doesn't force a re-fetch.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from scrapers import (
    CACHE_DIR, _fetch, normalize_key, fix_mojibake, canonical_player_key,
)

log = logging.getLogger(__name__)


# Spotrac mostly uses the same 3-letter MLB codes we do, but a handful
# differ. Map their version to our canonical_org() output. The two cells
# that bite are the White Sox (Spotrac CWS, we canonicalize to CHW) and
# any short-form team code (SF/SD/TB/KC) — though those don't actually
# appear in Spotrac's IFA tracker, they're still here as belt-and-
# suspenders for any other Spotrac page that might reuse the same
# normalization.
_SPOTRAC_TEAM_OVERRIDES: dict[str, str] = {
    "CWS": "CHW",   # Chicago White Sox
    "WSH": "WSN",   # Washington Nationals
    "SD":  "SDP",   # San Diego Padres
    "SF":  "SFG",   # San Francisco Giants
    "TB":  "TBR",   # Tampa Bay Rays
    "KC":  "KCR",   # Kansas City Royals
}


def _normalize_spotrac_org(raw: str | None) -> str | None:
    if not raw:
        return None
    code = raw.strip().upper()
    return _SPOTRAC_TEAM_OVERRIDES.get(code, code)


def _parse_bonus(raw: str | None) -> int | None:
    """Parse a dollar amount from Spotrac's display format.

    Handles "$6,500,000", "$50,000", "-", or empty. Returns None for
    missing values rather than 0 so the UI can distinguish "no data" from
    "$0 bonus". Stripped of commas/$/whitespace before int conversion."""
    if not raw:
        return None
    s = raw.strip().replace(",", "").replace("$", "")
    if not s or s in ("-", "—"):
        return None
    # Some rows say "Pool" or carry a note instead of a number — drop.
    if not re.fullmatch(r"-?\d+", s):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def scrape_spotrac_ifa(year: int, force: bool = False) -> list[dict]:
    """Fetch + parse one signing-period page. Returns a list of dicts:

        {
          "year":         int,
          "player_name":  str,    # Unicode (Spotrac serves UTF-8)
          "player_key":   str,    # normalize_key + canonical_player_key
          "spotrac_id":   str | None,   # numeric id from the player link
          "position":     str | None,
          "org":          str | None,   # canonical 3-letter MLB code
          "country":      str | None,
          "bonus_usd":    int  | None,
          "pool_pct":     float | None,
        }

    Empty list on fetch or parse failure (the run logs why).
    """
    url = f"https://www.spotrac.com/mlb/international/_/year/{year}"
    cache_key = f"spotrac_ifa_{year}"
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200 or not fr.body:
        log.warning("spotrac IFA %d: fetch failed (status=%d)", year, fr.status)
        return []

    soup = BeautifulSoup(fr.body, "html.parser")
    table = soup.find("table", id="table")
    if not table:
        log.warning("spotrac IFA %d: no <table id='table'> on page", year)
        return []
    tbody = table.find("tbody")
    if not tbody:
        log.warning("spotrac IFA %d: table has no tbody", year)
        return []

    out: list[dict] = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue
        # Player name + Spotrac id (from the link href).
        a = tds[0].find("a")
        name_raw = (a.get_text(strip=True) if a else tds[0].get_text(strip=True))
        name = fix_mojibake(name_raw)
        if not name:
            continue
        spotrac_id = None
        if a and a.get("href"):
            m = re.search(r"/id/(\d+)/", a["href"])
            spotrac_id = m.group(1) if m else None

        position = (tds[1].get_text(strip=True) or None)

        # Year column — usually matches the page year but trust the row.
        try:
            row_year = int(tds[2].get_text(strip=True))
        except (ValueError, TypeError):
            row_year = year

        # Team cell holds an <img> + a 2-3-letter abbreviation as text.
        team_text = tds[3].get_text(" ", strip=True)
        team_abbr = None
        # The text usually looks like " LAD"; pull the last whitespace-delimited token.
        for tok in reversed(team_text.split()):
            if 2 <= len(tok) <= 3 and tok.isupper():
                team_abbr = tok
                break
        org = _normalize_spotrac_org(team_abbr)

        country = fix_mojibake(tds[4].get_text(" ", strip=True)) or None
        bonus = _parse_bonus(tds[5].get_text(strip=True))

        pool_pct = None
        pool_raw = tds[6].get_text(strip=True).rstrip("%")
        try:
            pool_pct = float(pool_raw)
        except (TypeError, ValueError):
            pool_pct = None

        out.append({
            "year":        row_year,
            "player_name": name,
            "player_key":  canonical_player_key(normalize_key(name)),
            "spotrac_id":  spotrac_id,
            "position":    position,
            "org":         org,
            "country":     country,
            "bonus_usd":   bonus,
            "pool_pct":    pool_pct,
        })

    log.info("spotrac IFA %d: parsed %d signings (%d with bonus)",
             year, len(out), sum(1 for r in out if r["bonus_usd"] is not None))
    return out


def scrape_spotrac_ifa_range(years: Iterable[int], force: bool = False) -> list[dict]:
    """Convenience: fetch + parse multiple seasons in one shot. Useful
    for the run_monthly bootstrap that wants 2021–current in one call."""
    all_rows: list[dict] = []
    for y in years:
        all_rows.extend(scrape_spotrac_ifa(y, force=force))
    return all_rows


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------
# The raw signing list feeds two derived views used on farm pages:
#   * a {org: {year: total_bonus}} matrix for "IFA spending per year",
#   * a {player_key: bonus_usd} map for IFA-method acquisitions enrichment.

def build_ifa_bonus_by_key(signings: list[dict]) -> dict[str, int]:
    """Collapse a multi-year signing list to {player_key: bonus_usd}.

    When the same key appears across years (player re-signs / multi-row
    fixture errors on Spotrac's side), the latest year's value wins so
    a 2026-cycle signing supersedes any 2024 placeholder row."""
    by_key: dict[tuple[str, int], int] = {}
    for s in signings:
        if s.get("bonus_usd") is None or not s.get("player_key"):
            continue
        by_key[(s["player_key"], s["year"] or 0)] = s["bonus_usd"]
    out: dict[str, int] = {}
    for (key, year), bonus in sorted(by_key.items(), key=lambda kv: kv[0][1]):
        out[key] = bonus
    return out


def build_org_ifa_spending(signings: list[dict]) -> dict[str, dict[int, dict]]:
    """Aggregate signings into per-org per-year spending totals.

    Returns:
      {
        "BOS": {
          2024: {"total_usd": 5_750_000, "signings": 12, "top_bonus": 3_500_000},
          2025: {"total_usd": 4_200_000, "signings": 10, "top_bonus": 2_100_000},
        },
        ...
      }

    Includes every signing on Spotrac — graded prospects, org filler, and
    everything between — so the resulting totals reflect the org's actual
    cycle commitment rather than just the share that landed on our list."""
    out: dict[str, dict[int, dict]] = {}
    for s in signings:
        org = s.get("org")
        year = s.get("year")
        bonus = s.get("bonus_usd")
        if not org or not year or bonus is None:
            continue
        bucket = out.setdefault(org, {}).setdefault(year, {
            "total_usd": 0, "signings": 0, "top_bonus": 0, "top_player": None,
        })
        bucket["total_usd"] += bonus
        bucket["signings"]  += 1
        if bonus > bucket["top_bonus"]:
            bucket["top_bonus"]  = bonus
            bucket["top_player"] = s.get("player_name")
    return out
