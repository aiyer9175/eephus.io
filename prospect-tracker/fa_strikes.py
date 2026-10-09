# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Option strike prices and types from Spotrac's player contract pages.

Owner answer M14-4 (2026-09-25): build a Spotrac contract-page strike parser.

WHY. The 2026-07-30 Spotrac redesign of the free-agent AVAILABLE page dropped the
"CLUB / $12.0M" tail of the Type column (fa_sources._parse_available_compact), so
a pending option arrives with its type and no strike. On the 2027 class that left
6 of 46 pending options with a price, and every unpriced club or player option
fell back to the flat P(enter) prior and an unpriced row on the Club Ledger's
options calendar. The player's own contract page still prints the option year:

    https://www.spotrac.com/mlb/player/_/id/<spotrac_id>/<slug>

Its first `table.contract-breakdown` carries one row per contract season (Year,
Age, YOS, Status, Payroll Annual, ...). The Status cell of an option season holds
`<div class="option option-club">Club</div>` (option-player "Player",
option-mutual "Mutual", option-early-termination "Opt-Out"). An opt-out season is
preceded by a full-width note row, "PLAYER OPT-OUT: AVAILABLE <strong>2027</strong>,
2 YR, $84,000,000 REMAINING".

WHAT THE STRIKE IS, by type (the units fa_market.enter_probability_v2 and
fa_market.option_value_usd price against):
  club_option / player_option / mutual_option   that season's salary (Payroll Annual)
  opt_out                                       the remaining guarantee the note row
                                                prints; no note, no strike

RULES.
  - Cached: every page goes through scrapers._fetch under its own cache key
    (spotrac_player_<id>), with a 7-day TTL (scrapers._cache_ttl_for_key).
  - Rate-limited: at most STRIKE_MAX_FETCHES network reads per run, at least
    STRIKE_FETCH_SPACING_S apart (on top of _fetch's own spacing); a cached
    page costs nothing and is never throttled.
  - Provenance per row: strike_src, strike_url, strike_as_of (the cached page's
    date), strike_type and strike_type_raw (the page's status label).
  - A known strike is kept: when the page yields none (no table, no option
    season, a fetch failure, the fetch budget spent), the row keeps the strike
    the AVAILABLE page printed, else the one stored for it on the previous run,
    with that source named. Nothing is ever invented.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

STRIKE_MAX_FETCHES = 80
STRIKE_FETCH_SPACING_S = 1.5
CONTRACT_URL = "https://www.spotrac.com/mlb/player/_/id/{sid}/{slug}"

SRC_CONTRACT_PAGE = "spotrac_contract_page"
SRC_AVAILABLE_PAGE = "spotrac_available_page"
SRC_KEPT_PRIOR = "kept_prior_run"

# The status label of an option season, matched on the option-* class first and
# on the label text second. Anything else (UFA, an arbitration step, a vesting
# clause) is not an option season this parser prices.
_CLASS_TYPES = {
    "option-club": "club_option",
    "option-player": "player_option",
    "option-mutual": "mutual_option",
    "option-early-termination": "opt_out",
}
_TEXT_TYPES = (("opt-out", "opt_out"), ("opt out", "opt_out"), ("mutual", "mutual_option"),
               ("club", "club_option"), ("player", "player_option"))
_MONEY_RE = re.compile(r"\$\s*([\d,]+)")
_OPT_OUT_NOTE_RE = re.compile(
    r"OPT-OUT:\s*AVAILABLE\s*(\d{4})\s*,\s*(\d+)\s*YR\s*,\s*\$\s*([\d,]+)\s*REMAINING", re.I)


def _money(text: str | None) -> int | None:
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    try:
        v = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return v if v > 0 else None


def _status_type(cell) -> tuple[str | None, str | None]:
    """(option type, raw label) for one Status cell; (None, label) when the
    season is not an option season."""
    div = cell.find(class_=re.compile(r"^option"))
    raw = re.sub(r"\s+", " ", (div or cell).get_text(" ", strip=True)).strip() or None
    if div is not None:
        for cls in div.get("class") or []:
            if cls in _CLASS_TYPES:
                return _CLASS_TYPES[cls], raw
    low = (raw or "").lower()
    for needle, kind in _TEXT_TYPES:
        if needle in low:
            return kind, raw
    return None, raw


def parse_contract_page(html: str, option_year: int) -> dict | None:
    """The option on season ``option_year`` from one contract page, or None.

    Returns {"strike_usd", "strike_type", "strike_type_raw", "strike_basis"} and,
    for an opt-out, "remaining_years"."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="contract-breakdown")
    if table is None or table.find("tbody") is None:
        return None
    heads = [re.sub(r"\s+", " ", th.get_text(" ", strip=True)).lower()
             for th in (table.find("thead") or table).find_all("th")]
    try:
        i_status = heads.index("status")
    except ValueError:
        return None
    i_pay = next((i for i, h in enumerate(heads) if h.startswith("payroll")), None)
    note = None
    for tr in table.find("tbody").find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if len(tds) == 1:
            m = _OPT_OUT_NOTE_RE.search(re.sub(r"\s+", " ", tds[0].get_text(" ", strip=True)))
            if m and int(m.group(1)) == int(option_year):
                note = (int(m.group(2)), int(m.group(3).replace(",", "")))
            continue
        m_year = re.match(r"\s*(\d{4})", tds[0].get_text(" ", strip=True)) if tds else None
        if not m_year or int(m_year.group(1)) != int(option_year) or len(tds) <= i_status:
            continue
        kind, raw = _status_type(tds[i_status])
        if kind is None:
            return None
        if kind == "opt_out":
            if note is None:
                return None
            return {"strike_usd": note[1], "strike_type": kind, "strike_type_raw": raw,
                    "strike_basis": "remaining_guarantee", "remaining_years": note[0]}
        strike = _money(tds[i_pay].get_text(" ", strip=True)) if i_pay is not None and i_pay < len(tds) else None
        if strike is None:
            return None
        return {"strike_usd": strike, "strike_type": kind, "strike_type_raw": raw,
                "strike_basis": "option_year_salary"}
    return None


def _is_cached(cache_key: str) -> bool:
    """True when scrapers._fetch would serve this page from disk (present and
    inside its TTL), so reading it costs no request and needs no spacing."""
    import scrapers
    p = scrapers.CACHE_DIR / f"{cache_key}.html"
    try:
        return (time.time() - p.stat().st_mtime) <= scrapers._cache_ttl_for_key(cache_key)
    except OSError:
        return False


def _page_as_of(cache_key: str) -> str | None:
    import scrapers
    p = scrapers.CACHE_DIR / f"{cache_key}.html"
    try:
        return datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
    except OSError:
        return None


def fetch_contract_option(spotrac_id: str, slug: str | None, option_year: int,
                          force: bool = False, fetch=None) -> tuple[dict | None, dict]:
    """(parsed option or None, {"url", "cache_key", "from_cache", "status", "as_of"})."""
    import scrapers
    fetch = fetch or scrapers._fetch
    url = CONTRACT_URL.format(sid=spotrac_id, slug=slug or "player")
    key = f"spotrac_player_{spotrac_id}"
    fr = fetch(url, key, force=force)
    meta = {"url": url, "cache_key": key, "from_cache": bool(getattr(fr, "from_cache", False)),
            "status": getattr(fr, "status", 0), "as_of": None}
    if meta["status"] != 200 or not getattr(fr, "body", ""):
        return None, meta
    meta["as_of"] = _page_as_of(key) or date.today().isoformat()
    try:
        return parse_contract_page(fr.body, option_year), meta
    except Exception:                                     # noqa: BLE001
        log.exception("strike parse failed on %s", url)
        return None, meta


def row_basis(fa_type: str | None) -> str:
    """The strike's unit for a class row's option type."""
    return "remaining_guarantee" if fa_type == "opt_out" else "option_year_salary"


def _clear(row: dict) -> None:
    for k in ("strike_src", "strike_url", "strike_as_of", "strike_type", "strike_type_raw",
              "strike_basis"):
        row.pop(k, None)


def attach_strikes(rows: list[dict], class_year: int, prior: dict | None = None, *,
                   force: bool = False, fetch=None, sleep=time.sleep,
                   max_fetches: int = STRIKE_MAX_FETCHES) -> dict:
    """Stamp option_price_usd and its provenance on every pending option row, in
    place. ``prior`` is {player_key: stored row payload} from the previous run.
    Returns counts by source."""
    counts = {SRC_CONTRACT_PAGE: 0, SRC_AVAILABLE_PAGE: 0, SRC_KEPT_PRIOR: 0,
              "none": 0, "fetched": 0, "type_disagrees": 0, "basis_mismatch": 0}
    prior = prior or {}
    n_net = 0
    last_net = None
    for r in rows:
        if (r.get("fa_type") or "ufa") == "ufa":
            continue
        # The strike the row arrived with. On a fresh AVAILABLE scrape it is the
        # page's own; on a stored row (restrike_stored) it may be an earlier
        # contract-page strike, which falls to the kept-prior branch with its
        # own provenance rather than being relabelled.
        page_price = r.get("option_price_usd")
        page_src, page_as_of = r.get("strike_src"), r.get("strike_as_of")
        _clear(r)
        got, meta = None, None
        if r.get("spotrac_id"):
            cached = not force and _is_cached(f"spotrac_player_{r['spotrac_id']}")
            if cached or n_net < max_fetches:
                if last_net is not None and not cached:
                    wait = STRIKE_FETCH_SPACING_S - (time.monotonic() - last_net)
                    if wait > 0:
                        sleep(wait)
                got, meta = fetch_contract_option(r["spotrac_id"], r.get("spotrac_slug"),
                                                  class_year, force=force, fetch=fetch)
                if not meta["from_cache"] and meta["status"] != 0:
                    n_net += 1
                    counts["fetched"] += 1
                    last_net = time.monotonic()
                elif not meta["from_cache"]:
                    last_net = time.monotonic()
        if got and r.get("fa_type") not in (None, "unknown") \
                and got["strike_basis"] != row_basis(r.get("fa_type")):
            # An opt-out on one page and a salary option on the other price in
            # different units (a remaining guarantee against one season), so
            # the page's figure is not this row's strike.
            counts["basis_mismatch"] += 1
            got = None
        if got:
            r["option_price_usd"] = got["strike_usd"]
            r.update({"strike_src": SRC_CONTRACT_PAGE, "strike_url": meta["url"],
                      "strike_as_of": meta["as_of"], "strike_type": got["strike_type"],
                      "strike_type_raw": got["strike_type_raw"],
                      "strike_basis": got["strike_basis"]})
            if got["strike_type"] != r.get("fa_type"):
                counts["type_disagrees"] += 1
                if r.get("fa_type") in (None, "unknown"):
                    r["fa_type"] = got["strike_type"]
            counts[SRC_CONTRACT_PAGE] += 1
            continue
        if page_price and page_src in (None, SRC_AVAILABLE_PAGE):
            r["option_price_usd"] = page_price
            r.update({"strike_src": SRC_AVAILABLE_PAGE,
                      "strike_as_of": page_as_of or date.today().isoformat()})
            counts[SRC_AVAILABLE_PAGE] += 1
            continue
        old = prior.get(r.get("player_key")) or {}
        if old.get("option_price_usd") and old.get("fa_type") == r.get("fa_type"):
            r["option_price_usd"] = old["option_price_usd"]
            r["strike_src"] = SRC_KEPT_PRIOR
            for k in ("strike_url", "strike_as_of", "strike_type", "strike_type_raw", "strike_basis"):
                if old.get(k) is not None:
                    r[k] = old[k]
            counts[SRC_KEPT_PRIOR] += 1
            continue
        r["option_price_usd"] = None
        counts["none"] += 1
    log.info("fa strikes %d: %s", class_year, counts)
    return counts


def restrike_stored(class_year: int, *, force: bool = False, fetch=None,
                    sleep=time.sleep) -> dict:
    """Attach strikes to the class rows already stored, without re-scraping the
    AVAILABLE page: the strike fields, option_price_usd and the v1 P(enter)
    that prices it change; membership, status, fetched_at and every other
    field stay as stored. Returns the counts plus "rows_updated"."""
    import json
    import fa_class
    import storage
    stored = {k: p for (k, yr), p in storage.load_fa_class_players(class_year).items()
              if yr == class_year}
    rows = [dict(p) for _, p in sorted(stored.items())]
    counts = attach_strikes(rows, class_year, stored, force=force, fetch=fetch, sleep=sleep)
    changed = []
    for r in rows:
        if r.get("status") == "pending_option":
            ep = fa_class.exercise_probability(r)
            r["enter_prob"], r["enter_prob_method"] = ep["enter_prob"], ep["method"]
        if r != stored.get(r.get("player_key")):
            changed.append(r)
    with storage.connect() as con:
        for r in changed:
            con.execute("UPDATE fa_class_players SET payload_json = ? "
                        "WHERE player_key = ? AND class_year = ?",
                        (json.dumps(r), r["player_key"], class_year))
    counts["rows_updated"] = len(changed)
    log.info("fa strikes %d: %d stored rows updated", class_year, len(changed))
    return counts


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Attach Spotrac contract-page option "
                                 "strikes to a stored FA class (no AVAILABLE re-scrape)")
    ap.add_argument("class_year", type=int)
    ap.add_argument("--force", action="store_true", help="bypass the page cache")
    a = ap.parse_args()
    print(restrike_stored(a.class_year, force=a.force))
