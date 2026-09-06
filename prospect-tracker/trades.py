# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Trade detection.

A prospect is "traded" when his organization changes between snapshots
from different sources or dates. We detect this with two complementary
signals:

  1. Authoritative — MLB Stats API transactions endpoint
       GET statsapi.mlb.com/api/v1/transactions
           ?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
     Returns every roster transaction across baseball. We filter to
     typeCode == "TR" (trade) and match by MLBAM ID against the players
     we track. Gives us an exact trade date plus from-team / to-team.

  2. Fallback — org-change inference
     When we have snapshots for a player showing org=PIT on 2026-01-22
     and org=BAL on 2026-05-13, that's almost certainly a trade. We
     record one with source="inferred" and date_range = (earliest_after,
     latest_before) — i.e., we know the trade happened between the last
     snapshot showing the old org and the first snapshot showing the new
     one. If the authoritative API also catches it, we prefer that
     record and drop the inferred one.

Why both? Prospect-only trades (no current MLB roster players involved)
are sometimes absent from the transactions endpoint for hours or days
after announcement, especially around the deadline when traffic is
high. The org-change inference catches those even when the API misses.
Conversely, the API catches trades that haven't yet been reflected in
any prospect ranking source's published list.

Output: a list of Trade dataclasses per player, sorted oldest to newest,
so the front-end can render them as markers on the FV timeline.
"""

from __future__ import annotations

import logging
import re as _re
import time
import unicodedata as _uc
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import requests

from scrapers import Snapshot
from stats import resolve_mlbam_id  # reuses the cached Chadwick lookup

log = logging.getLogger(__name__)

# --- Description ↔ player_name validation ---------------------------------
# Historically the trades table picked up records under the wrong player_key
# whenever resolve_mlbam_id returned the ID of a same-name player (e.g.
# Thomas White's player_key getting Thomas Hatch's transactions). The fix is
# to validate the API's free-text description against the player's stored
# name at insert time: if the last name (with hyphen-component fallback) is
# absent from the description, the record almost certainly belongs to a
# different player and we drop it.

_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _normalize_for_match(s: str) -> str:
    s = (s or "").replace("�", "")  # leftover encoding sentinel
    s = _uc.normalize("NFKD", s)
    s = "".join(c for c in s if not _uc.combining(c))
    s = s.lower()
    # Drop apostrophes/periods entirely (D'Shawn → dshawn; A.J. → aj).
    s = _re.sub(r"[.\'’`]", "", s)
    # Everything else non-alphanumeric becomes whitespace.
    s = _re.sub(r"[^a-z0-9]+", " ", s)
    return s


def _last_name_keys(player_name: str) -> set[str]:
    n = _normalize_for_match(player_name)
    toks = [t for t in n.split() if t and t not in _NAME_SUFFIXES]
    if len(toks) < 2:
        return set()
    # Include the last token, plus the second-to-last when the player has
    # 3+ tokens — covers hyphenated last names like "Smith-Njigba" where
    # the API sometimes prints only "Smith".
    if len(toks) >= 3:
        return {toks[-1], toks[-2]}
    return {toks[-1]}


def description_references_player(description: str, player_name: str) -> bool:
    """True when the trade description's text plausibly refers to player_name.

    Last-name match only — diminutives like Jacob/Jake and Michael/Mike are
    common, but shared surnames are the most reliable signal that the API
    record actually belongs to this person. Returns True when player_name
    can't be parsed so we don't reject otherwise-valid trades for fringe
    name formats."""
    lasts = _last_name_keys(player_name)
    if not lasts:
        return True
    d_tokens = set(_normalize_for_match(description).split())
    return any(lt in d_tokens for lt in lasts)

MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
RATE_LIMIT_SECONDS = 0.5


@dataclass
class Trade:
    player_key: str
    trade_date: str          # YYYY-MM-DD. For inferred, the latest possible date.
    from_org: str | None
    to_org: str | None
    source: str              # "mlb_api" | "inferred"
    description: str | None  # full transaction text from API; None for inferred
    date_range_start: str | None  # for "inferred" only: earliest possible date
    date_range_end: str | None    # for "inferred" only: latest possible date


# ---------------------------------------------------------------------------
# Signal 1 — authoritative MLB transactions API
# ---------------------------------------------------------------------------

def fetch_trades_in_window(start_date: str, end_date: str,
                            max_workers: int = 8) -> list[dict]:
    """
    Return every trade-type transaction in the [start, end] window.

    The transactions endpoint has a per-request range limit of about 30
    days, so we chunk longer windows. Chunks are fetched in parallel —
    historical data is read-only (older chunks never change) and the API
    handles concurrent reads happily, so a 7-year backfill that used to
    take ~30s of sequential requests now finishes in ~4s.

    Returns the raw API records; matching to our tracked players happens
    downstream.
    """
    import concurrent.futures

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        return []

    # Build the chunk list up-front so order is preserved and we can
    # parallelize the fetches.
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=29), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    def _fetch(chunk: tuple[date, date]) -> list[dict]:
        c_start, c_end = chunk
        url = (
            f"{MLB_STATS_API}/transactions"
            f"?startDate={c_start.isoformat()}&endDate={c_end.isoformat()}"
        )
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("transactions API %s -> %s failed: %s",
                        c_start.isoformat(), c_end.isoformat(), e)
            return []
        out: list[dict] = []
        for tx in data.get("transactions", []):
            # Only the API's "TR" typeCode is a trade. The previous
            # filter ALSO accepted any transaction with from_team !=
            # to_team, which polluted the trades list with waiver
            # claims (CU), Rule 5 selections/returns (SE/SC), contract
            # purchases (PU), and outrights (OUT) — all of which have
            # from/to teams set but are not trades. Those events still
            # surface in the unified transaction-history view via the
            # per-player /transactions endpoint (`derive_transactions`),
            # they just don't pretend to be trades anymore.
            if tx.get("typeCode") == "TR":
                out.append(tx)
        return out

    all_records: list[dict] = []
    worker_count = max(1, min(max_workers, len(chunks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as ex:
        for chunk_records in ex.map(_fetch, chunks):
            all_records.extend(chunk_records)

    log.info("MLB transactions API: %d trade records in [%s..%s] "
             "(%d chunks, %d workers)",
             len(all_records), start_date, end_date, len(chunks), worker_count)
    return all_records


def trades_from_api(
    transactions: list[dict],
    tracked_players: dict[str, tuple[str, int | None]],
) -> list[Trade]:
    """
    Convert raw API records to Trade objects, filtered to players we track.

    Args:
      transactions: raw records from fetch_trades_in_window
      tracked_players: {player_key: (player_name, mlbam_id_or_None)}

    The MLBAM ID is the join key. If we don't have an ID for a tracked
    player (lookup failed), they're skipped here and the inferred
    fallback may still catch their trade.
    """
    # Build reverse index: mlbam_id -> player_key
    id_to_key = {
        mlbam: key for key, (_name, mlbam) in tracked_players.items()
        if mlbam is not None
    }

    trades: list[Trade] = []
    rejected_mismatch = 0
    for tx in transactions:
        person = tx.get("person") or {}
        mlbam = person.get("id")
        if mlbam not in id_to_key:
            continue
        player_key = id_to_key[mlbam]
        player_name = tracked_players[player_key][0]
        description = tx.get("description")
        # Defensive: reject records whose description doesn't reference our
        # player. Protects against stale/wrong ID mappings where a different
        # player's transaction would otherwise land under this player_key
        # (e.g. Thomas White getting Thomas Hatch's roster moves).
        if description and not description_references_player(description, player_name):
            rejected_mismatch += 1
            log.debug("rejecting api trade for %s (id=%s) — desc mismatch: %s",
                      player_name, mlbam, description[:120])
            continue
        from_team = ((tx.get("fromTeam") or {}).get("name"))
        to_team   = ((tx.get("toTeam")   or {}).get("name"))
        trades.append(Trade(
            player_key=player_key,
            trade_date=tx.get("date") or tx.get("effectiveDate") or "",
            from_org=from_team,
            to_org=to_team,
            source="mlb_api",
            description=description,
            date_range_start=None,
            date_range_end=None,
        ))
    log.info("matched %d API trades to tracked players (rejected %d desc-mismatch)",
             len(trades), rejected_mismatch)
    return trades


# ---------------------------------------------------------------------------
# Signal 2 — org-change inference from snapshot history
# ---------------------------------------------------------------------------

# Org abbreviations and full names need to be reconciled. Sources are
# inconsistent: FanGraphs uses "PIT" while MLB.com uses "Pirates" while
# Baseball America writes "Pittsburgh". Normalize to a canonical short
# code so comparisons work.
ORG_ALIASES = {
    "pittsburgh": "PIT", "pirates": "PIT",
    "texas": "TEX", "rangers": "TEX",
    "athletics": "ATH", "oakland": "ATH", "ath": "ATH",
    "milwaukee": "MIL", "brewers": "MIL",
    "baltimore": "BAL", "orioles": "BAL",
    "detroit": "DET", "tigers": "DET",
    "seattle": "SEA", "mariners": "SEA",
    "colorado": "COL", "rockies": "COL",
    # Sources disagree on Washington: snapshots use "WSN", the MLB API
    # uses "Washington Nationals". Canonicalize both to "WSN" so the
    # dedup path treats inferred (WSN) and API (Washington Nationals)
    # records as the same canonical destination.
    "washington": "WSN", "nationals": "WSN", "wsh": "WSN",
    "tampa bay": "TBR", "rays": "TBR", "tb": "TBR",
    "cleveland": "CLE", "guardians": "CLE",
    "toronto": "TOR", "blue jays": "TOR",
    "ny mets": "NYM", "mets": "NYM",
    "ny yankees": "NYY", "yankees": "NYY",
    "los angeles dodgers": "LAD", "dodgers": "LAD",
    "los angeles angels": "LAA", "angels": "LAA",
    "san francisco": "SFG", "giants": "SFG",
    "san diego": "SDP", "padres": "SDP",
    "arizona": "ARI", "diamondbacks": "ARI",
    "atlanta": "ATL", "braves": "ATL",
    "boston": "BOS", "red sox": "BOS",
    "chicago cubs": "CHC", "cubs": "CHC",
    "chicago white sox": "CHW", "white sox": "CHW",
    "cincinnati": "CIN", "reds": "CIN",
    "houston": "HOU", "astros": "HOU",
    "kansas city": "KCR", "royals": "KCR",
    "minnesota": "MIN", "twins": "MIN",
    "miami": "MIA", "marlins": "MIA",
    "philadelphia": "PHI", "phillies": "PHI",
    "st louis": "STL", "st. louis": "STL", "cardinals": "STL",
}


# 3-letter codes that sources alias to a different canonical form.
# Sources disagree on Washington: snapshots use "WSN", others use "WSH".
# Athletics dropped their "Oakland" prefix mid-2024 — treat OAK as ATH.
# The MLB Stats API uses shorter 2-3 char team codes (AZ, KC, SD, SF, TB,
# CWS) than the prospect-ranking sources (ARI, KCR, SDP, SFG, TBR, CHW)
# we keep as canonical. Normalize the API codes onto our canonical form
# so per-level rosters and the org_summary line up.
_CODE_REMAP = {
    "WSH": "WSN",
    "OAK": "ATH",
    "AZ":  "ARI",
    "CWS": "CHW",
    "KC":  "KCR",
    "SD":  "SDP",
    "SF":  "SFG",
    "TB":  "TBR",
}


#: MLB club ids never change; club NAMES do. StatsAPI has called Arizona
#: "D-backs" since 2008, Cleveland "Indians" through 2021 and Montreal "Expos"
#: through 2004, and none of the three resolves through the name aliases. Every
#: one of them was being silently dropped by callers that resolve a club by name
#: and then guard on `len(org) <= 3`: the alias table returns the input
#: unchanged, the guard sees a 7-character string and skips the row.
#:
#: Measured 2026-09-06 across the 27 cached standings files: 46 club-seasons
#: lost this way, and Arizona was the only one of 30 rows in the served
#: team_outlook carrying a null current-season block, which is a 75-68 contender
#: missing from the live wild-card picture.
#:
#: Built from tjstats.MLBAM_TEAM_ID_TO_ABBR, whose keys are STRINGS while every
#: StatsAPI teamRecord id is an int, so the cast is load-bearing.
_ORG_BY_MLBAM_ID: dict | None = None


def _org_by_id() -> dict:
    global _ORG_BY_MLBAM_ID
    if _ORG_BY_MLBAM_ID is None:
        try:
            import tjstats
            raw = getattr(tjstats, "MLBAM_TEAM_ID_TO_ABBR", {}) or {}
        except Exception:                                   # noqa: BLE001
            raw = {}
        out = {}
        for k, v in raw.items():
            try:
                out[int(k)] = canonical_org(v) or v
            except (TypeError, ValueError):
                continue
        _ORG_BY_MLBAM_ID = out
    return _ORG_BY_MLBAM_ID


def canonical_org_from_id(team_id, fallback_name: str | None = None) -> str | None:
    """A 3-letter org code from a StatsAPI club id, falling back to the name.

    PREFER THIS over `canonical_org(name)` anywhere a StatsAPI payload is being
    read, because ids are stable and names are not. The fallback exists for
    fixtures and for payloads that carry a name and no id; it is not a reason to
    skip the id when one is present.
    """
    if team_id is not None:
        try:
            got = _org_by_id().get(int(team_id))
        except (TypeError, ValueError):
            got = None
        if got:
            return got
    return canonical_org(fallback_name) if fallback_name else None


def canonical_org(raw: str | None) -> str | None:
    """Normalize any org string to a 3-letter code. Pass-through if already short.

    Handles:
      - codes already in 3-4 char uppercase form ("BOS", "CHW")
      - 3-letter aliases (WSH→WSN, OAK→ATH) so the source disagreement
        doesn't fragment the same canonical destination across dedup
      - exact-match keys in ORG_ALIASES (e.g. "boston", "red sox")
      - full team names like "Boston Red Sox" — token-search using
        word boundaries so the longest matching alias wins WITHOUT
        catching substrings inside other words. ("Comets" must not
        match the "mets" alias, which previously mapped a Dodgers
        AAA affiliate name to NYM.)
    """
    if not raw:
        return None
    s = raw.strip()
    if len(s) <= 4 and s.isupper():
        return _CODE_REMAP.get(s, s)
    low = s.lower()
    if low in ORG_ALIASES:
        return ORG_ALIASES[low]
    # Token-search fallback with word boundaries. Try longer keys first so
    # "chicago white sox" beats "chicago" for the White Sox.
    import re as _re_local
    for key in sorted(ORG_ALIASES, key=len, reverse=True):
        if _re_local.search(rf"\b{_re_local.escape(key)}\b", low):
            return ORG_ALIASES[key]
    return s


def infer_trades_from_snapshots(snapshots: list[Snapshot]) -> list[Trade]:
    """
    Walk a player's snapshots chronologically. When the canonical org
    changes between adjacent snapshots, record an inferred trade.

    The trade_date is bracketed: it must have happened *after* the last
    snapshot showing the old org and *on or before* the first snapshot
    showing the new org. We store both bounds in date_range_start /
    date_range_end and set trade_date to the upper bound (latest
    possible date) so it sorts intuitively.
    """
    # Group by player_key
    by_player: dict[str, list[Snapshot]] = {}
    for s in snapshots:
        by_player.setdefault(s.player_key, []).append(s)

    trades: list[Trade] = []
    for player_key, snaps in by_player.items():
        # Sort chronologically. Ties: order doesn't matter for org-change
        # detection since same-day snapshots from different sources
        # showing different orgs are usually just metadata disagreement,
        # not a same-day trade. We collapse same-day to majority org.
        from collections import Counter, defaultdict
        snaps_sorted = sorted(snaps, key=lambda s: s.snapshot_date)

        by_date: dict[str, list[str]] = defaultdict(list)
        for s in snaps_sorted:
            org = canonical_org(s.org)
            if org is not None:
                by_date[s.snapshot_date].append(org)

        # Reduce same-day to majority org
        date_to_org: list[tuple[str, str]] = []
        for d in sorted(by_date.keys()):
            orgs = by_date[d]
            if not orgs:
                continue
            majority = Counter(orgs).most_common(1)[0][0]
            date_to_org.append((d, majority))

        # Find transitions
        for i in range(1, len(date_to_org)):
            prev_date, prev_org = date_to_org[i - 1]
            curr_date, curr_org = date_to_org[i]
            if prev_org == curr_org:
                continue
            trades.append(Trade(
                player_key=player_key,
                trade_date=curr_date,  # latest possible
                from_org=prev_org,
                to_org=curr_org,
                source="inferred",
                description=None,
                date_range_start=prev_date,
                date_range_end=curr_date,
            ))
    log.info("inferred %d trades from org changes", len(trades))
    return trades


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile_trades(api_trades: list[Trade],
                     inferred_trades: list[Trade]) -> list[Trade]:
    """
    Merge API and inferred trades, preferring API when both fire for the
    same (player, approximate-date) pair.

    Two trades are considered "the same event" if:
      - Same player_key, AND
      - The API trade_date falls within the inferred trade's date range
        (inclusive)

    We keep the API record (more accurate date, plus description text)
    and drop the inferred one.
    """
    # Index API trades by player_key for fast lookup
    api_by_player: dict[str, list[Trade]] = {}
    for t in api_trades:
        api_by_player.setdefault(t.player_key, []).append(t)

    output: list[Trade] = list(api_trades)
    for inf in inferred_trades:
        matched = False
        for api_t in api_by_player.get(inf.player_key, []):
            if (inf.date_range_start <= api_t.trade_date <= inf.date_range_end
                    and _orgs_match(api_t.from_org, inf.from_org)
                    and _orgs_match(api_t.to_org, inf.to_org)):
                matched = True
                break
        if not matched:
            output.append(inf)

    # Sort by trade_date ascending so timeline rendering is straightforward
    output.sort(key=lambda t: (t.player_key, t.trade_date))
    log.info("reconciled: %d API + %d inferred -> %d total trades "
             "(%d API-only, %d inferred-only)",
             len(api_trades), len(inferred_trades), len(output),
             sum(1 for t in output if t.source == "mlb_api"),
             sum(1 for t in output if t.source == "inferred"))
    return output


def _orgs_match(a: str | None, b: str | None) -> bool:
    """Loose org match: canonical-equal or one contains the other (case-insensitive)."""
    if not a or not b:
        return False
    ca = canonical_org(a) or ""
    cb = canonical_org(b) or ""
    if ca == cb:
        return True
    return ca.lower() in cb.lower() or cb.lower() in ca.lower()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_trades(
    snapshots: list[Snapshot],
    tracked_players: dict[str, tuple[str, int | None]] | None = None,
    skip_api: bool = False,
) -> list[Trade]:
    """
    Top-level: take all snapshots, return all detected trades.

    Args:
      snapshots: every snapshot we have
      tracked_players: {player_key: (player_name, mlbam_id_or_None)}
                       Required for API match; if None, we skip the API.
      skip_api: bypass the API and rely on inferred only. Useful for
                offline runs or when the API is rate-limited.
    """
    if not snapshots:
        return []

    inferred = infer_trades_from_snapshots(snapshots)

    if skip_api or not tracked_players:
        log.info("skipping API; using inferred trades only")
        return sorted(inferred, key=lambda t: (t.player_key, t.trade_date))

    # Date window: from earliest snapshot to today
    earliest = min(s.snapshot_date for s in snapshots)
    today = date.today().isoformat()
    api_records = fetch_trades_in_window(earliest, today)
    api_trades = trades_from_api(api_records, tracked_players)

    return reconcile_trades(api_trades, inferred)


def trade_to_dict(t: Trade) -> dict:
    return asdict(t)
