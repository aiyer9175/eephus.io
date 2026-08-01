# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""External ingestion for the MLB Free Agency module.

Spotrac pages (verified shapes, June 2026):

  AVAILABLE class (current winter; owner-pointed source):
      https://www.spotrac.com/mlb/free-agents/available/_/year/{Y}
      <table id="table"> — Player / Pos / Age / Prev Team / Prev AAV /
      Type / Market Value AAV / Bat-Throw / Prev WAR. The Type column is
      the option-status taxonomy (UFA, CLUB / $x, PLAYER / $x, MUTUAL /
      $x, OPT-OUT / $x, CONDITIONAL-*) — exactly what class construction
      needs to flag LOCKED vs option-pending membership.

  HISTORICAL class (signed view; stable 2015→present):
      https://www.spotrac.com/mlb/free-agents/_/year/{Y}
      tables[0] (no id) — From / (logo) / To / Player (+<small>QO</small>) /
      Pos / Yrs / Value / AAV. Remaining-unsigned tables reuse the
      available layout but SHUFFLE COLUMN ORDER between instances, so
      every parser here maps cells by HEADER NAME, never by position.

  CBT tax + payroll ledgers:
      https://www.spotrac.com/mlb/tax/_/year/{Y}      (tax payroll, space
          vs threshold, estimated bill, repeat-payor status)
      https://www.spotrac.com/mlb/payroll/_/year/{Y}  (total allocations,
          active/injured/retained/buried splits)

Spotrac's year param = the season the contracts cover, which matches the
module's class_year convention (class_year 2027 = the 2026-27 offseason).

Conventions mirror spotrac.py: `_fetch` disk cache under .cache/, BS4
html.parser, `_normalize_spotrac_org`-style org mapping, money parsing
that returns None (never 0) for missing values, explicit empty-list
failure modes with logged reasons.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from scrapers import _fetch, fix_mojibake, normalize_key, canonical_player_key
from spotrac import _normalize_spotrac_org

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Cell parsers
# --------------------------------------------------------------------------- #

_MONEY_M_RE = re.compile(r"^\$?\s*(-?\d+(?:\.\d+)?)\s*M$", re.IGNORECASE)


def _parse_money(raw: str | None) -> int | None:
    """Dollars from either Spotrac display form: "$210,000,000" or the
    millions shorthand the Type column uses ("$55.3M"). None for missing /
    "-" — never 0, so the UI can tell "no data" from "$0"."""
    if not raw:
        return None
    s = raw.strip()
    if not s or s in ("-", "—"):
        return None
    m = _MONEY_M_RE.match(s.replace(",", ""))
    if m:
        return int(round(float(m.group(1)) * 1_000_000))
    s = s.replace(",", "").replace("$", "")
    if not re.fullmatch(r"-?\d+", s):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    s = raw.strip().replace(",", "")
    if not s or s in ("-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# Spotrac Type-column → the module's fa_type taxonomy. The class engine
# treats anything except "ufa" as option-pending membership.
_FA_TYPE_MAP = {
    "UFA": "ufa",
    "OPT-OUT": "opt_out",
    "PLAYER": "player_option",
    "CLUB": "club_option",
    "MUTUAL": "mutual_option",
    "CONDITIONAL-PLAYER": "conditional_player_option",
    "CONDITIONAL-CLUB": "conditional_club_option",
    # Compact-layout pill tokens (2026-07-30 redesign). Same taxonomy, the
    # abbreviations Spotrac prints inside the status pill.
    "ETO": "opt_out",           # early termination option
    "PLYR": "player_option",
    "MUT": "mutual_option",
}


def _parse_fa_type(raw: str | None) -> dict:
    """"OPT-OUT / $55.3M" → {fa_type: "opt_out", option_price_usd: 55300000}.
    Unrecognized labels pass through verbatim under fa_type_raw so a new
    Spotrac taxonomy value degrades loudly (visible in data) not silently."""
    out = {"fa_type": "ufa", "fa_type_raw": (raw or "").strip() or None, "option_price_usd": None}
    if not raw or not raw.strip():
        return out
    parts = [p.strip() for p in raw.split("/")]
    head = parts[0].upper()
    out["fa_type"] = _FA_TYPE_MAP.get(head, "unknown")
    if len(parts) > 1:
        out["option_price_usd"] = _parse_money(parts[1])
    return out


def _player_cell_meta(td) -> dict:
    """Name, Spotrac id+slug (from the player link), and the inline QO
    marker (<small>QO</small> on signed rows)."""
    a = td.find("a")
    name_raw = a.get_text(" ", strip=True) if a else td.get_text(" ", strip=True)
    qo = False
    small = td.find("small")
    if small and "QO" in small.get_text(strip=True).upper():
        qo = True
        name_raw = name_raw.replace(small.get_text(" ", strip=True), "").strip()
    # The cell's full text can include the QO marker even without <small>
    # separation in odd rows — strip a trailing standalone "QO" token.
    name = fix_mojibake(re.sub(r"\s+QO$", "", name_raw).strip())
    spotrac_id = slug = None
    if a and a.get("href"):
        m = re.search(r"/id/(\d+)/([a-z0-9-]+)", a["href"])
        if m:
            spotrac_id, slug = m.group(1), m.group(2)
    return {
        "player_name": name,
        "player_key": canonical_player_key(normalize_key(name)) if name else None,
        "spotrac_id": spotrac_id,
        "spotrac_slug": slug,
        "qo": qo,
    }


def _header_map(table) -> dict[str, int]:
    """Normalized header text → column index. Spotrac shuffles column
    order between table instances, so positions are never trusted."""
    head = table.find("thead")
    out: dict[str, int] = {}
    if not head:
        return out
    for i, th in enumerate(head.find_all("th")):
        text = re.sub(r"\s+", " ", th.get_text(" ", strip=True)).lower()
        text = re.sub(r"\s*\(\d+\)$", "", text)          # "Player (229)" → "player"
        text = re.sub(r"\s*\$[\d,.]+.*$", "", text)      # "Value $2,996,…" → "value"
        out[text.strip()] = i
    return out


def _col(hmap: dict[str, int], *names: str) -> int | None:
    for n in names:
        if n in hmap:
            return hmap[n]
    return None


# --------------------------------------------------------------------------- #
# FA class pages
# --------------------------------------------------------------------------- #

_AGE_RE = re.compile(r"Age:\s*([\d.]+)", re.IGNORECASE)
# Logo basenames are not uniform: mlb_nym.png, mil.png, cle_2022.png,
# ath_2025.png. Optional mlb_ prefix, optional _YYYY rebrand suffix.
_TEAM_IMG_RE = re.compile(r"/(?:mlb_)?([a-z]{2,3})(?:_\d{4})?\.(?:png|svg|jpg)", re.IGNORECASE)


def _parse_available_compact(table, year: int) -> list[dict]:
    """The 2-column AVAILABLE layout Spotrac switched to on 2026-07-30.

    One "Players" cell now carries what used to be six columns: a status
    pill (UFA / ETO / PLYR / CLUB), the player link, <strong>position</strong>,
    a team logo, YOE and Age. Column 2 is "Previous AAV".

    Fields the compact layout NO LONGER PUBLISHES anywhere on the page, and
    which therefore come back None rather than stale: option strike price
    (the old "CLUB / $12.0M" tail), market value AAV, bat/throw, prev WAR.
    A missing pill means a plain pending UFA (verified: 31 of 218 rows on
    the 2027 board, Sonny Gray / Joc Pederson / Eugenio Suarez et al).
    """
    out: list[dict] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        cell = tds[0]
        meta = _player_cell_meta(cell)
        if not meta["player_name"]:
            continue
        pill = cell.select_one(".pill-start")
        pill_txt = pill.get_text(strip=True) if pill else ""
        strong = cell.find("strong")
        img = cell.find("img")
        team = None
        if img and img.get("src"):
            m = _TEAM_IMG_RE.search(img["src"])
            if m:
                team = _normalize_spotrac_org(m.group(1).upper())
        age_m = _AGE_RE.search(cell.get_text(" ", strip=True))
        row = {
            "class_year": year,
            **meta,
            "position": strong.get_text(" ", strip=True) or None if strong else None,
            "age": float(age_m.group(1)) if age_m else None,
            "from_team": team,
            "prev_aav_usd": _parse_money(tds[1].get_text(strip=True)),
            "market_value_aav_usd": None,
            "bat_throw": None,
            "prev_war": None,
        }
        # No pill = plain pending UFA; _parse_fa_type maps "" to ufa already.
        row.update(_parse_fa_type(pill_txt))
        out.append(row)
    return out


def _parse_available_table(table, year: int) -> list[dict]:
    hmap = _header_map(table)
    i_player = _col(hmap, "player")
    i_pos = _col(hmap, "pos")
    i_age = _col(hmap, "age")
    i_prev = _col(hmap, "prev team")
    i_aav = _col(hmap, "prev aav")
    i_type = _col(hmap, "type")
    i_mkt = _col(hmap, "market value aav", "market value")
    i_bt = _col(hmap, "arm bat/throw", "bat/throw")
    i_war = _col(hmap, "prev war")
    if i_player is None or i_type is None:
        # Compact layout: one compound "Players" column + "Previous AAV".
        if _col(hmap, "players") is not None:
            rows = _parse_available_compact(table, year)
            if rows:
                return rows
            log.warning("fa available %d: compact layout parsed 0 rows", year)
            return []
        log.warning("fa available %d: unrecognized header set %s", year, sorted(hmap))
        return []
    out: list[dict] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(i_player, i_type):
            continue
        meta = _player_cell_meta(tds[i_player])
        if not meta["player_name"]:
            continue
        row = {
            "class_year": year,
            **meta,
            "position": tds[i_pos].get_text(" ", strip=True) or None if i_pos is not None and i_pos < len(tds) else None,
            "age": _parse_float(tds[i_age].get_text(strip=True)) if i_age is not None and i_age < len(tds) else None,
            "from_team": _normalize_spotrac_org(tds[i_prev].get_text(" ", strip=True).split()[-1]) if i_prev is not None and i_prev < len(tds) and tds[i_prev].get_text(strip=True) else None,
            "prev_aav_usd": _parse_money(tds[i_aav].get_text(strip=True)) if i_aav is not None and i_aav < len(tds) else None,
            "market_value_aav_usd": _parse_money(tds[i_mkt].get_text(strip=True)) if i_mkt is not None and i_mkt < len(tds) else None,
            "bat_throw": tds[i_bt].get_text(" ", strip=True) or None if i_bt is not None and i_bt < len(tds) else None,
            "prev_war": _parse_float(tds[i_war].get_text(strip=True)) if i_war is not None and i_war < len(tds) else None,
        }
        row.update(_parse_fa_type(tds[i_type].get_text(" ", strip=True)))
        out.append(row)
    return out


def scrape_spotrac_fa_available(year: int, force: bool = False) -> list[dict]:
    """The current-winter AVAILABLE board (pre-signing class membership
    with option-status taxonomy). Empty list on failure, reason logged."""
    url = f"https://www.spotrac.com/mlb/free-agents/available/_/year/{year}"
    fr = _fetch(url, f"spotrac_fa_avail_{year}", force=force)
    if fr.status != 200 or not fr.body:
        log.warning("fa available %d: fetch failed (status=%d)", year, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    table = soup.find("table", id="table")
    if not table:
        log.warning("fa available %d: no <table id='table'>", year)
        return []
    rows = _parse_available_table(table, year)
    log.info("fa available %d: %d players", year, len(rows))
    return rows


def _parse_signed_table(table, year: int) -> list[dict]:
    hmap = _header_map(table)
    i_from = _col(hmap, "from")
    i_to = _col(hmap, "to")
    i_player = _col(hmap, "player")
    i_pos = _col(hmap, "pos")
    i_yrs = _col(hmap, "yrs")
    i_val = _col(hmap, "value")
    i_aav = _col(hmap, "aav")
    if i_player is None or i_yrs is None or i_val is None:
        log.warning("fa class %d: unrecognized signed-table headers %s", year, sorted(hmap))
        return []
    out: list[dict] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(i_player, i_yrs, i_val):
            continue
        meta = _player_cell_meta(tds[i_player])
        if not meta["player_name"]:
            continue
        years = _parse_float(tds[i_yrs].get_text(strip=True))
        guarantee = _parse_money(tds[i_val].get_text(strip=True))
        out.append({
            "class_year": year,
            **meta,
            "position": tds[i_pos].get_text(" ", strip=True) or None if i_pos is not None and i_pos < len(tds) else None,
            "from_team": _normalize_spotrac_org(tds[i_from].get_text(" ", strip=True).split()[-1]) if i_from is not None and i_from < len(tds) and tds[i_from].get_text(strip=True) else None,
            "to_team": _normalize_spotrac_org(tds[i_to].get_text(" ", strip=True).split()[-1]) if i_to is not None and i_to < len(tds) and tds[i_to].get_text(strip=True) else None,
            "years": int(years) if years is not None and float(years).is_integer() else years,
            "guarantee_usd": guarantee,
            "aav_usd": _parse_money(tds[i_aav].get_text(strip=True)) if i_aav is not None and i_aav < len(tds) else None,
            # Spotrac lists minor-league / split signings with no guaranteed
            # value — kept (they ARE class outcomes) but flagged so the
            # market model trains on MLB-guarantee deals only.
            "mlb_deal": guarantee is not None and guarantee > 0,
        })
    return out


def scrape_spotrac_fa_class(year: int, force: bool = False) -> dict:
    """One historical class page → {"signed": [...], "unsigned": [...]}.

    tables[0] (no id) is the signed ledger; any id="table" instance with
    rows is the remaining-unsigned board (available layout, shuffled
    columns — handled by header mapping)."""
    url = f"https://www.spotrac.com/mlb/free-agents/_/year/{year}"
    fr = _fetch(url, f"spotrac_fa_class_{year}", force=force)
    if fr.status != 200 or not fr.body:
        log.warning("fa class %d: fetch failed (status=%d)", year, fr.status)
        return {"signed": [], "unsigned": []}
    soup = BeautifulSoup(fr.body, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        log.warning("fa class %d: no tables on page", year)
        return {"signed": [], "unsigned": []}
    signed = _parse_signed_table(tables[0], year)
    unsigned: list[dict] = []
    for t in tables[1:]:
        body = t.find("tbody")
        if body and body.find_all("tr"):
            unsigned.extend(_parse_available_table(t, year))
    log.info("fa class %d: %d signed, %d unsigned", year, len(signed), len(unsigned))
    return {"signed": signed, "unsigned": unsigned}


def scrape_fa_class_range(start_year: int, end_year: int, force: bool = False,
                          max_workers: int = 4) -> dict[int, dict]:
    """Parallel multi-winter backfill (per-year disk caches make re-runs
    free). Returns {class_year: {"signed": [...], "unsigned": [...]}}."""
    years = list(range(start_year, end_year + 1))
    out: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for year, res in zip(years, ex.map(lambda y: scrape_spotrac_fa_class(y, force=force), years)):
            out[year] = res
    return out


# --------------------------------------------------------------------------- #
# CBT tax + payroll ledgers
# --------------------------------------------------------------------------- #

def _team_from_cell(td) -> str | None:
    """Team cells render as logo + duplicated code ("LAD LAD") — take the
    last token and normalize to the canonical 3-letter org code."""
    text = td.get_text(" ", strip=True)
    if not text:
        return None
    return _normalize_spotrac_org(text.split()[-1])


def scrape_spotrac_tax(year: int, force: bool = False) -> list[dict]:
    """The CBT ledger: per-team tax payroll, space vs threshold, estimated
    bill, and repeat-payor status — the affordability engine's ground truth."""
    url = f"https://www.spotrac.com/mlb/tax/_/year/{year}"
    fr = _fetch(url, f"spotrac_tax_{year}", force=force)
    if fr.status != 200 or not fr.body:
        log.warning("spotrac tax %d: fetch failed (status=%d)", year, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("spotrac tax %d: no table", year)
        return []
    hmap = _header_map(table)
    i_team = _col(hmap, "team")
    i_status = _col(hmap, "status")
    i_tax = _col(hmap, "tax payroll")
    i_space = _col(hmap, "space")
    i_bill = _col(hmap, "tax bill estimated", "tax bill")
    if i_team is None or i_tax is None:
        log.warning("spotrac tax %d: unrecognized headers %s", year, sorted(hmap))
        return []
    out: list[dict] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(i_team, i_tax):
            continue
        team = _team_from_cell(tds[i_team])
        if not team:
            continue
        out.append({
            "season": year,
            "team": team,
            "payor_status_raw": tds[i_status].get_text(" ", strip=True) or None if i_status is not None and i_status < len(tds) else None,
            "tax_payroll_usd": _parse_money(tds[i_tax].get_text(strip=True)),
            "space_usd": _parse_money(tds[i_space].get_text(strip=True)) if i_space is not None and i_space < len(tds) else None,
            "est_tax_bill_usd": _parse_money(tds[i_bill].get_text(strip=True)) if i_bill is not None and i_bill < len(tds) else None,
        })
    log.info("spotrac tax %d: %d teams", year, len(out))
    return out


def scrape_spotrac_payroll(year: int, force: bool = False) -> list[dict]:
    """The payroll-allocations ledger (incl. future seasons — committed
    money for the affordability model's forward view)."""
    url = f"https://www.spotrac.com/mlb/payroll/_/year/{year}"
    fr = _fetch(url, f"spotrac_payroll_{year}", force=force)
    if fr.status != 200 or not fr.body:
        log.warning("spotrac payroll %d: fetch failed (status=%d)", year, fr.status)
        return []
    soup = BeautifulSoup(fr.body, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("spotrac payroll %d: no table", year)
        return []
    hmap = _header_map(table)
    i_team = _col(hmap, "team")
    i_total = _col(hmap, "total payroll allocations", "total payroll")
    i_active = _col(hmap, "active 26-man", "active")
    i_inj = _col(hmap, "injured")
    i_ret = _col(hmap, "retained")
    i_bur = _col(hmap, "buried")
    i_age = _col(hmap, "avg age team", "avg age")
    if i_team is None or i_total is None:
        log.warning("spotrac payroll %d: unrecognized headers %s", year, sorted(hmap))
        return []
    out: list[dict] = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(i_team, i_total):
            continue
        team = _team_from_cell(tds[i_team])
        if not team:
            continue
        out.append({
            "season": year,
            "team": team,
            "total_payroll_usd": _parse_money(tds[i_total].get_text(strip=True)),
            "active_usd": _parse_money(tds[i_active].get_text(strip=True)) if i_active is not None and i_active < len(tds) else None,
            "injured_usd": _parse_money(tds[i_inj].get_text(strip=True)) if i_inj is not None and i_inj < len(tds) else None,
            "retained_usd": _parse_money(tds[i_ret].get_text(strip=True)) if i_ret is not None and i_ret < len(tds) else None,
            "buried_usd": _parse_money(tds[i_bur].get_text(strip=True)) if i_bur is not None and i_bur < len(tds) else None,
            "avg_age": _parse_float(tds[i_age].get_text(strip=True)) if i_age is not None and i_age < len(tds) else None,
        })
    log.info("spotrac payroll %d: %d teams", year, len(out))
    return out


# --------------------------------------------------------------------------- #
# Aging / projection corpus — MLB StatsAPI league-wide season stats
# --------------------------------------------------------------------------- #
# One official source covers the whole modern era AND the current season
# (no Lahman publication lag; pybaseball's Lahman mirror is broken upstream
# anyway). playerPool=All returns every player-season, not just qualifiers.
# Age + per-season bWAR join in from B-Ref's war_daily tables by MLBAM id
# (war_daily's mlb_ID column) in fa_projection.build_corpus().

_STATSAPI_SEASON_URL = (
    "https://statsapi.mlb.com/api/v1/stats?stats=season&group={group}"
    "&season={season}&sportId=1&limit=5000&playerPool=All"
)


def fetch_statsapi_season_stats(season: int, group: str, force: bool = False) -> list[dict]:
    """Every MLB player-season stat line for one (season, group) — group is
    "hitting" or "pitching". Returns the raw `splits` records."""
    import json as _json
    url = _STATSAPI_SEASON_URL.format(group=group, season=season)
    fr = _fetch(url, f"fa_statsapi_{group}_{season}", force=force, accept_json=True)
    if fr.status != 200 or not fr.body:
        log.warning("statsapi season %s %d: fetch failed (status=%d)", group, season, fr.status)
        return []
    try:
        payload = _json.loads(fr.body)
        stats = payload.get("stats") or []
        return (stats[0].get("splits") or []) if stats else []
    except (ValueError, KeyError) as e:
        log.warning("statsapi season %s %d: parse failed (%s)", group, season, e)
        return []


def fetch_statsapi_season_range(first: int, last: int, force: bool = False,
                                max_workers: int = 6) -> dict:
    """{(season, group): splits} for both groups across a season range.
    Per-season disk caches make re-runs free."""
    jobs = [(s, g) for s in range(first, last + 1) for g in ("hitting", "pitching")]
    out: dict = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for (s, g), res in zip(jobs, ex.map(lambda j: fetch_statsapi_season_stats(*j, force=force), jobs)):
            out[(s, g)] = res
    return out


# --------------------------------------------------------------------------- #
# Baseball Savant park factors (embedded-JSON extraction; csv=true is
# ignored by the endpoint, the page embeds `var data = [...]`)
# --------------------------------------------------------------------------- #

_SAVANT_PF_URL = (
    "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"
    "?type=year&year={year}&batSide={bat_side}&stat=index_wOBA&condition=All&rolling="
)


def fetch_savant_park_factors(year: int, bat_side: str = "", force: bool = False) -> list[dict]:
    """Park-factor rows (100 = neutral) per venue: index_woba / index_hr /
    index_runs / ... bat_side "" (all), "L", or "R" for handedness splits."""
    import json as _json
    url = _SAVANT_PF_URL.format(year=year, bat_side=bat_side)
    fr = _fetch(url, f"savant_pf_{year}_{bat_side or 'all'}", force=force)
    if fr.status != 200 or not fr.body:
        log.warning("savant pf %d/%s: fetch failed (status=%d)", year, bat_side or "all", fr.status)
        return []
    m = re.search(r"var\s+data\s*=\s*(\[.*?\]);", fr.body, re.S)
    if not m:
        log.warning("savant pf %d/%s: embedded data array not found", year, bat_side or "all")
        return []
    try:
        return _json.loads(m.group(1))
    except ValueError as e:
        log.warning("savant pf %d/%s: JSON parse failed (%s)", year, bat_side or "all", e)
        return []
