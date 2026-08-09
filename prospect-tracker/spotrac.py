# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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


def scrape_spotrac_ifa_range(years: Iterable[int], force: bool = False,
                             max_workers: int = 4) -> list[dict]:
    """Convenience: fetch + parse multiple seasons in one shot. Useful
    for the run_monthly bootstrap that wants 2021-current in one call.

    Parallelized so a 5-year range (~5 sequential pages × 0.5s ≈ 2.5s)
    drops to one round-trip with workers."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    years_list = list(years)
    all_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_year = {ex.submit(scrape_spotrac_ifa, y, force=force): y
                          for y in years_list}
        for fut in as_completed(future_to_year):
            y = future_to_year[fut]
            try:
                all_rows.extend(fut.result())
            except Exception:
                log.exception("spotrac IFA worker failed for year %s", y)
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


# ---------------------------------------------------------------------------
# Team contract scraper — pulls AAV / per-year salary from Spotrac's
# yearly contract tables. Each team's roster lives on its own page, and
# each row carries:
#   - Player name + Spotrac id (from the cell's <a href>)
#   - Position (data-export attribute on cell 1)
#   - Per-year salary (data-export attribute on each year column)
# The page is FUTURE-only — it shows current-year salary plus the
# remaining contract years. Historical seasons (years already played)
# don't appear, so the realized-surplus pipeline still falls back to
# the league-min model for prior seasons.
# ---------------------------------------------------------------------------

# Spotrac team URL slugs — full hyphenated team names. Keyed by our
# canonical 3-letter codes so the consumer can iterate via _SPOTRAC_TEAM_SLUGS
# without re-resolving codes. ATH (Athletics) drops the "Oakland" prefix
# per the team's mid-2024 rename; all other slugs are the standard
# "<city>-<nickname>" form.
_SPOTRAC_TEAM_SLUGS: dict[str, str] = {
    "ARI": "arizona-diamondbacks",
    "ATL": "atlanta-braves",
    "ATH": "athletics",
    "BAL": "baltimore-orioles",
    "BOS": "boston-red-sox",
    "CHC": "chicago-cubs",
    "CHW": "chicago-white-sox",
    "CIN": "cincinnati-reds",
    "CLE": "cleveland-guardians",
    "COL": "colorado-rockies",
    "DET": "detroit-tigers",
    "HOU": "houston-astros",
    "KCR": "kansas-city-royals",
    "LAA": "los-angeles-angels",
    "LAD": "los-angeles-dodgers",
    "MIA": "miami-marlins",
    "MIL": "milwaukee-brewers",
    "MIN": "minnesota-twins",
    "NYM": "new-york-mets",
    "NYY": "new-york-yankees",
    "PHI": "philadelphia-phillies",
    "PIT": "pittsburgh-pirates",
    "SDP": "san-diego-padres",
    "SEA": "seattle-mariners",
    "SFG": "san-francisco-giants",
    "STL": "st-louis-cardinals",
    "TBR": "tampa-bay-rays",
    "TEX": "texas-rangers",
    "TOR": "toronto-blue-jays",
    "WSN": "washington-nationals",
}


def _parse_year_header(th_text: str) -> int | None:
    """Header cells render the literal year ("2026") or a label ("Pos").
    Returns the int year when parseable, None otherwise."""
    if not th_text:
        return None
    s = th_text.strip()
    if s.isdigit() and 2000 <= int(s) <= 2100:
        return int(s)
    return None


# Contract-STATUS placeholders that occupy a year cell instead of a dollar
# figure. Spotrac renders these with data-export="0" while the token itself
# lives in the cell TEXT, so a digit-only guard reads them as a $0 salary.
# See _parse_team_contract_table for the defect this exists to close.
#
# Cell text can carry a leading numeric sort key ("-2PRE-ARB", "5UFA",
# "-1ARB 1"), so the prefix is stripped before matching.
_YEAR_CELL_SORT_PREFIX_RE = re.compile(r"^-?\d+(?=[A-Za-z])")
_YEAR_CELL_STATUS_RE = re.compile(
    r"^(PRE-ARB|ARB\s*[1-4](?:\s*\(S2\))?|ARB|UFA|RFA|TBD)$", re.I)


def _year_cell_status(cell_text: str) -> str | None:
    """The contract-status token in a year cell, or None when the cell is a
    money cell (including a genuine "$0"). Normalized to upper case with
    single spaces so "arb 2 (s2)" and "ARB 2 (S2)" agree."""
    s = _YEAR_CELL_SORT_PREFIX_RE.sub("", (cell_text or "").strip())
    s = re.sub(r"\s+", " ", s).strip()
    if not s or not _YEAR_CELL_STATUS_RE.match(s):
        return None
    return s.upper()


def _parse_team_contract_table(table, team_slug: str) -> list[dict]:
    """Parse one Spotrac yearly contract table (dataTable-active /
    dataTable-injured / dataTable-dead share the same structure).
    Returns one dict per row with the per-year salary map, the per-year
    contract-STATUS map, plus derived AAV / total / years_remaining /
    signed_through fields.

    DEFECT FIXED 2026-08-08. A year cell holding a contract-status
    placeholder ("PRE-ARB", "ARB 2", "ARB 3 (S2)", "UFA", "TBD") renders
    with data-export="0" and the token in the cell text. The old guard was
    `if not raw or not raw.isdigit(): continue`, and "0" IS a digit, so
    every such cell was stored as `salary_by_year[year] = 0`. Measured on
    the 30 cached team pages: 700 of 1,405 rows (49.8%) carried at least
    one phantom zero, which inflated `years_remaining` and `signed_through`
    on all of them and produced $478.7M of absolute AAV error (Ke'Bryan
    Hayes read 5 years / signed_through 2030 / $7.08M AAV against a true
    4 / 2029 / $8.85M). Those fields feed
    bayes_trade_value._estimate_salary_mm, so the error reached served
    trade values.

    The discriminator is the cell TEXT, not data-export: across the cached
    pages 1,347 of the 1,370 data-export="0" cells are status tokens and 23
    are a genuine "$0". Money cells are the ones that do NOT match
    _YEAR_CELL_STATUS_RE, so a real $0 still prices as $0.

    Status tokens are RETAINED rather than dropped: they are the only
    per-player arbitration-year labels available anywhere in this tree
    (there is no service-time ground truth -- see
    bayes_trade_value.py:4498), and the /arbitration/ module reads them.

    Row inclusion is a strict SUPERSET of the old behavior: a row is kept
    when it has any real salary OR any status year. Previously a row whose
    only year cells were placeholders was kept with a phantom all-zero
    salary map, so dropping it here would have removed players; instead it
    is kept with an empty salary map and a populated status map."""
    rows: list[dict] = []
    thead = table.find("thead")
    if not thead:
        return rows
    # Build column-index → year map by walking the header row.
    header_years: dict[int, int] = {}
    th_cells = thead.find_all("th")
    for idx, th in enumerate(th_cells):
        year = _parse_year_header(th.get_text(strip=True))
        if year is not None:
            header_years[idx] = year
    if not header_years:
        return rows

    tbody = table.find("tbody")
    if not tbody:
        return rows
    for tr in tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        # Cell 0 holds player name + Spotrac link. data-export is the
        # canonical display name ("Kyle Tucker"); the cell's text adds
        # a sort prefix and a duplicate ("Tucker Kyle Tucker").
        name_cell = tds[0]
        name = (name_cell.get("data-export") or "").strip()
        if not name:
            link = name_cell.find("a")
            name = (link.get_text(strip=True) if link else
                    name_cell.get_text(strip=True))
        if not name:
            continue
        name = fix_mojibake(name)
        spotrac_id = None
        link = name_cell.find("a")
        if link and link.get("href"):
            m = re.search(r"/id/(\d+)/", link["href"])
            spotrac_id = m.group(1) if m else None
        # Position from cell 1's data-export attribute (cleaner than the
        # text, which mixes SP/DH etc.).
        position = None
        if len(tds) > 1:
            position = (tds[1].get("data-export") or "").strip() or None
        # Per-year cells — walk header_years. A cell is either MONEY
        # (data-export = integer dollars) or a contract-STATUS placeholder
        # (data-export "0" with the token in the text). The text decides;
        # see the docstring for why data-export alone cannot.
        salary_by_year: dict[int, int] = {}
        status_by_year: dict[int, str] = {}
        for col_idx, year in header_years.items():
            if col_idx >= len(tds):
                continue
            cell = tds[col_idx]
            status = _year_cell_status(cell.get_text(strip=True))
            if status is not None:
                status_by_year[year] = status
                continue
            raw = (cell.get("data-export") or "").strip()
            if not raw or not raw.isdigit():
                continue
            try:
                salary_by_year[year] = int(raw)
            except ValueError:
                continue
        if not salary_by_year and not status_by_year:
            # Neither money nor a status on file — player is either on a
            # 1-year deal that already ended (rare) or unsigned. Skip.
            continue
        # Every derived field below prices REAL DOLLARS ONLY. A status year
        # is a year the club controls at a price not yet set; counting it as
        # a $0 contract year is what produced the phantom AAV/term above.
        years_remaining = len(salary_by_year)
        total_usd = sum(salary_by_year.values())
        # AAV — the canonical "annual average value" is total / years.
        # For deferral-heavy deals (e.g., Ohtani) Spotrac's per-year
        # cash flow shown here already reflects the present-value
        # smoothing, so the simple mean is consistent with what the
        # site reports as AAV.
        aav_usd = total_usd // years_remaining if years_remaining else 0
        # Signed-through year = max PRICED year on file. A club-control year
        # with no figure yet is not a year the player is signed through.
        signed_through = max(salary_by_year) if salary_by_year else None
        # Current-year salary — picked off the lowest priced year in the map
        # so the consumer doesn't need to know what the "current" year
        # is at scrape time.
        current_year = min(salary_by_year) if salary_by_year else None
        salary_usd = salary_by_year.get(current_year) if current_year else None
        # Club-control years carrying an arbitration label, earliest first.
        # The /arbitration/ module's Spotrac label source.
        arb_years = sorted(y for y, s in status_by_year.items()
                           if s.startswith("ARB") or s == "PRE-ARB")
        rows.append({
            "player_name":      name,
            "player_key":       canonical_player_key(normalize_key(name)),
            "spotrac_id":       spotrac_id,
            "position":         position,
            "team_slug":        team_slug,
            "salary_usd":       salary_usd,
            "aav_usd":          aav_usd,
            "total_usd":        total_usd,
            "salary_by_year":   salary_by_year,
            "status_by_year":   status_by_year,
            "control_years":    arb_years,
            "years_remaining":  years_remaining,
            "signed_through":   signed_through,
            "current_year":     current_year,
        })
    return rows


# The three tables that carry CONTRACT money. This set is deliberately narrow
# and is the one build_contracts_by_key consumes.
CONTRACT_TABLE_IDS = ("dataTable-active", "dataTable-injured", "dataTable-dead")

# Tables that carry club-control STATUS but not (usually) contract money: the
# "Minor" roster where optioned players live, plus the small retained /
# restricted / reserve tables. 428 rows across the 30 cached pages.
#
# READ FOR STATUS ONLY, never folded into the contract set. Measured 2026-08-09:
# widening scrape_spotrac_team_contracts to include them adds 300 players (289
# with no salary dollars at all) but CHANGES three existing served contracts,
# two of them large - Nolan Arenado's AAV moves $5.5M -> $27.36M and Nick
# Castellanos's $0.3M -> $19.7M, because their retained-salary rows outrank
# their active rows under build_contracts_by_key's highest-AAV tiebreak.
#
# Whether an acquiring club should be charged the retained portion is a contract
# question with its own blast radius on served trade values, and it is NOT an
# arbitration question. So the arbitration module reads these tables for their
# ARB / PRE-ARB tokens and the contract set stays byte-identical.
#
# OPEN, for a future session: those two AAVs may be wrong TODAY on the narrow
# set. The retained-salary semantics were never adjudicated.
STATUS_TABLE_IDS = ("table", "dataTable-retained", "dataTable-restricted",
                    "dataTable-reserve-personal")


def scrape_spotrac_team_statuses(team_slug: str,
                                 force: bool = False) -> list[dict]:
    """Rows from the club-control tables that carry STATUS but not money.

    Same parser, different tables, and deliberately a different function: the
    contract set must not grow by a side effect of an arbitration change. See
    STATUS_TABLE_IDS for the measurement that motivated the split.
    """
    url = f"https://www.spotrac.com/mlb/{team_slug}/yearly/"
    fr = _fetch(url, f"spotrac_team_{team_slug}", force=force)
    if fr.status != 200 or not fr.body:
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    out: list[dict] = []
    for table_id in STATUS_TABLE_IDS:
        t = soup.find("table", id=table_id)
        if t is not None:
            out.extend(_parse_team_contract_table(t, team_slug))
    return out


def scrape_spotrac_team_contracts(team_slug: str,
                                   force: bool = False) -> list[dict]:
    """Fetch + parse one team's Spotrac yearly contract page. Returns a
    list of dicts (see _parse_team_contract_table). Includes the active
    roster + injured-list + dead-money tables (every player the team is
    paying), but skips the org-level summary table.

    Returns [] on fetch / parse failure with a logged warning so the
    pipeline can continue without contract data for that team."""
    url = f"https://www.spotrac.com/mlb/{team_slug}/yearly/"
    cache_key = f"spotrac_team_{team_slug}"
    fr = _fetch(url, cache_key, force=force)
    if fr.status != 200 or not fr.body:
        log.warning("spotrac team %s: fetch failed (status=%d)",
                    team_slug, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    out: list[dict] = []
    # Three sub-tables share the per-row structure; walk each.
    for table_id in ("dataTable-active", "dataTable-injured", "dataTable-dead"):
        t = soup.find("table", id=table_id)
        if t is None:
            continue
        out.extend(_parse_team_contract_table(t, team_slug))
    return out


def scrape_all_spotrac_contracts(force: bool = False,
                                 max_workers: int = 6) -> list[dict]:
    """Walk every team's yearly contract page. Returns one merged list.

    Bulk-fetches in parallel via ThreadPoolExecutor. Cold-cache: ~30
    pages × ~0.5s ÷ 6 workers ≈ 3s. Warm-cache: near-instant.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    slugs = list(_SPOTRAC_TEAM_SLUGS.items())
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_team = {
            ex.submit(scrape_spotrac_team_contracts, slug, force): team_code
            for team_code, slug in slugs
        }
        for fut in as_completed(future_to_team):
            team_code = future_to_team[fut]
            try:
                rows.extend(fut.result())
            except Exception:
                log.exception("spotrac contracts worker failed for %s", team_code)
    log.info("spotrac contracts: %d player-rows across %d teams",
             len(rows), len(_SPOTRAC_TEAM_SLUGS))
    return rows


def build_contracts_by_key(rows: list[dict]) -> dict[str, dict]:
    """Collapse multi-team rows to {player_key: contract_dict}. When a
    player appears on multiple team pages (rare — Spotrac updates fast
    so a mid-season trade usually only shows on the destination team),
    keep the row with the highest AAV as a defensive tiebreak."""
    out: dict[str, dict] = {}
    for r in rows:
        key = r.get("player_key")
        if not key:
            continue
        prev = out.get(key)
        if prev is None or (r.get("aav_usd") or 0) > (prev.get("aav_usd") or 0):
            out[key] = r
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
