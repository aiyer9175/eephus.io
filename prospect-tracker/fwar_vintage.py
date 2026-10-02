# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The frozen per-season fWAR vintage: its builder and its reader.

fWAR label epoch, precondition E3 part 1 (docs/efv-2026-09-17/
FWAR_LABEL_EPOCH_GATE.md parts 1, 3, 7 and 8). The label of the epoch is
PUBLISHED fWAR, FanGraphs' WAR as MLB's StatsAPI sabermetrics feed carries it,
FROZEN PER SEASON. This module writes and reads the one committed artifact
that holds it, data/fwar_vintage.json, and nothing else reads the feed for the
label.

WHAT A FROZEN SEASON HOLDS. Per season and per group (hitting, pitching): the
source URL, the group, `fetched_at`, the HTTP status, the sha256 of the raw
response body, the row counters, the stint-guard receipt (saber_feed's
resolve_groups: a multi-row id resolves to its unique numTeams > 1 total or is
refused and listed), and the rows themselves as {mlbam: [values]} in the order
of that group's `fields`. Values are stored exactly as the feed carries them;
a STRING where a number belongs is refused to null and counted
(`n_string_refused`), the rule saber_feed.run_value applies. Each group carries
a `content_sha256` over its fields and rows, each season a `content_sha256`
over its groups, and the file a `vintage_id` that names the label build: the
date of the newest `fetched_at` plus 12 hex characters of a sha256 over every
season's hash. The gate's part 8 `fwar` registry row and the step Z entry carry
it, and EPOCH_RUN's step D + U names it in the fingerprint's `label=` term as
`fwar@<vintage_id>`; this module only provides it.

THE FIELDS. Hitting: war, rar, the six RUN_PARTS, and (orchestrator note EB4,
for the eBR gate's incumbent inputs) wSb, ubr, wGdp and plateAppearances, plus
the split's numTeams; then the rest of what the hitting group publishes (woba,
wRaa, wRc, wRcPlus, spd), because a frozen season is never refetched.
Pitching (orchestrator note of 2026-10-01, for the Part 9
component projections): war, rar, fip, xfip, ra9War, gmli, exli, pli, inli,
eraMinus, fipMinus, md and sd, plus numTeams. A field the feed does not carry
on a row is stored as null and never invented: the pitching group carries no
innings, starts or games, and on every cached season 2011 to 2026 the hitting
group carries no plateAppearances, so that column is null until the feed
publishes it. `field_presence` reports the share of rows carrying each field.

THE RULES (builder):
  1. A season once frozen is NEVER overwritten. A run that names a frozen
     season is refused whole; `refreeze=True` (CLI --refreeze) is the only way
     past it and this program never uses it.
  2. The season must be complete. A past year is complete; the current year is
     complete only after its regular season's last day (REGULAR_SEASON_END; the
     2026 regular season ended 2026-09-27); a later year is refused.
  3. The builder never reads .cache payloads as the vintage. It fetches each
     group straight from StatsAPI (no credits, no FanGraphs HTML) through a
     fetcher that bypasses the scraper cache, and the fetcher is injected so a
     test never touches the network.
  4. All or nothing. A non-200 response, an unparseable body, a body at the
     feed's row cap (possibly truncated), a season of the feed's era with no
     rows, or a group under MIN_ROWS rows fails the run and nothing is written.
  5. The write is atomic (a sibling temp file, then os.replace).
  6. THE PRE-2011 PATH (E3 part 5, owner answer O4: "Cache 2000-2010 (22
     calls, no credits)"). The builder accepts 2000 to 2010 beside the feed's
     known era (FEED_FIRST_SEASON 2011): 11 seasons x 2 groups = the 22 calls
     of O4. Before 2011 each season calls PITCHING FIRST, so on a run that
     starts at 2000 the very first call is the pre-2011 pitching probe. A
     pre-2011 group whose answer is HTTP 200 with no rows is not a failure: it
     is RECORDED AS ABSENT, with the response it got (the HTTP status, the
     body's sha256 and the body itself up to ABSENT_BODY_MAX characters), and
     it is frozen like any other block (never refetched, never overwritten).
     A season with one group absent has basis `mixed`, both absent `absent`,
     and `fwar_seasons()` serves neither: every door of war_source's fwar
     provider keeps the incumbent value on such a season and counts it, and a
     downstream consumer whose cohort touches one stamps `war_basis: mixed`
     and never `fwar` (FWAR_LABEL_EPOCH_GATE.md part 4.1 note 3; part 7 row
     K). `war_basis(seasons)` is that stamp. A pre-2011 non-200, unparseable,
     capped or partial (under MIN_ROWS) answer still fails the run (rule 4):
     only a clean empty answer means "the feed does not publish this".

THE READER. `load()` (memoised in `_CACHE`, the test seam, like ewar.load),
`available()`, `fwar_seasons()` (the seasons whose every group is frozen),
`side_targets()` and `season_totals()`, the maps war_source's `fwar` provider
serves from. A player-season's fWAR is the sum of its groups' published war,
the same summing rule the bWAR aggregate applies across its two frames.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, NamedTuple

import saber_feed

ROOT = Path(__file__).resolve().parent
VINTAGE_PATH = ROOT / "data" / "fwar_vintage.json"
SCHEMA = "fwar_vintage/1"

#: The two groups, in the feed's names, and the war_source side each one prices.
GROUPS: tuple[str, ...] = ("hitting", "pitching")
SIDE_GROUP = {"bat": "hitting", "pit": "pitching"}

#: The first season the feed is known to publish both groups ([R1]: it joins at
#: 100.0% on MLBAM in every season 2011 to 2025 and is cached 2011 to 2026).
FEED_FIRST_SEASON = 2011

#: The earliest season the builder accepts (O4: the pre-2011 cache, 2000-2010).
FIRST_ACCEPTED_SEASON = 2000

#: How much of an empty pre-2011 response body an absent block keeps verbatim.
ABSENT_BODY_MAX = 4096

#: The last day of each regular season the builder may meet as the CURRENT
#: year. A current year missing here is refused as in progress.
REGULAR_SEASON_END: dict[int, _dt.date] = {2026: _dt.date(2026, 9, 27)}

#: A frozen group holds at least this many rows (the smallest cached group,
#: 2020 hitting, holds 620). Fewer is a partial response, refused.
MIN_ROWS = 300

#: Seconds between two calls of one run (StatsAPI is unauthenticated).
CALL_PAUSE_SECONDS = 1.0

HITTING_FIELDS: tuple[str, ...] = (("war", "rar") + tuple(saber_feed.RUN_PARTS)
                                   + ("wSb", "ubr", "wGdp", "plateAppearances", "numTeams")
                                   + ("woba", "wRaa", "wRc", "wRcPlus", "spd"))
PITCHING_FIELDS: tuple[str, ...] = tuple(saber_feed.PITCHING_FIELDS) + ("numTeams",)
FIELDS = {"hitting": HITTING_FIELDS, "pitching": PITCHING_FIELDS}

#: Fields read off the split rather than off its `stat` block.
_SPLIT_FIELDS = ("numTeams",)

BUILD_CMD = "python tools/build_fwar_vintage.py --freeze 2000-2026 --write"


class FreezeError(RuntimeError):
    """A freeze that must not write: the message names the season and the cause."""


class FetchResponse(NamedTuple):
    status: int
    body: bytes


# ---------------------------------------------------------------------------
# the fetcher (network; never the scraper cache)
# ---------------------------------------------------------------------------

def http_fetch(url: str) -> FetchResponse:
    """One direct GET. Never reads or writes .cache. status 0 on a network error."""
    import requests
    try:
        from scrapers import HEADERS
        headers = dict(HEADERS)
    except Exception:   # noqa: BLE001 - the header set is a courtesy, not a need
        headers = {}
    headers["Accept"] = "application/json"
    try:
        resp = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException:
        return FetchResponse(0, b"")
    return FetchResponse(int(resp.status_code), resp.content or b"")


# ---------------------------------------------------------------------------
# hashing and identity
# ---------------------------------------------------------------------------

def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


def group_content_sha(block: dict) -> str:
    """sha256 over a group's fields and rows (canonical JSON)."""
    return _sha({"fields": block.get("fields"), "rows": block.get("rows"),
                 "status": block.get("status")})


def season_content_sha(season_block: dict) -> str:
    return _sha({g: (season_block.get(g) or {}).get("content_sha256") for g in GROUPS})


def vintage_id(blob: dict) -> str:
    """The label build's name: newest fetched_at date + 12 hex of a sha256 over
    every season's content hash. Empty string for an empty vintage."""
    seasons = blob.get("seasons") or {}
    if not seasons:
        return ""
    digest = _sha({s: (b or {}).get("content_sha256") for s, b in sorted(seasons.items())})
    newest = max(str(g.get("fetched_at") or "")
                 for b in seasons.values() for g in (b.get(k) or {} for k in GROUPS))
    return f"{newest[:10]}-{digest[:12]}"


# ---------------------------------------------------------------------------
# the builder
# ---------------------------------------------------------------------------

def season_complete(season: int, today: _dt.date) -> tuple[bool, str]:
    """(complete, reason). See rule 2 of the module docstring."""
    season = int(season)
    if season < FIRST_ACCEPTED_SEASON:
        return False, f"{season} is before the first accepted season {FIRST_ACCEPTED_SEASON}"
    if season < today.year:
        return True, "a past season"
    if season > today.year:
        return False, f"{season} has not been played"
    end = REGULAR_SEASON_END.get(season)
    if end is None:
        return False, f"{season} is the current season and its regular-season end is not registered"
    if today <= end:
        return False, f"{season} is in progress (its regular season ends {end.isoformat()})"
    return True, f"the regular season ended {end.isoformat()}"


def _stored_value(v):
    """(value as the feed carries it, refused?) A string or a bool is refused."""
    if v is None:
        return None, False
    if isinstance(v, (str, bool)):
        return None, True
    if isinstance(v, (int, float)):
        return (None, True) if (isinstance(v, float) and v != v) else (v, False)
    return None, True


def group_rows(splits: list, group: str) -> dict:
    """Resolve the stint groups and lay the rows out under the group's fields."""
    fields = FIELDS[group]
    rows, ambiguous, n_multi = saber_feed.resolve_groups(splits)
    out: dict[str, list] = {}
    n_refused = 0
    for pid in sorted(rows):
        row = rows[pid]
        st = row.get("stat") or {}
        vals = []
        for f in fields:
            raw = row.get(f) if f in _SPLIT_FIELDS else st.get(f)
            v, refused = _stored_value(raw)
            n_refused += int(refused)
            vals.append(v)
        out[str(pid)] = vals
    return {"rows": out, "ambiguous_ids": ambiguous, "n_multi_team": n_multi,
            "n_string_refused": n_refused}


def freeze_group(season: int, group: str, fetch: Callable[[str], FetchResponse],
                 now: Callable[[], str]) -> dict:
    """Fetch and freeze one (season, group). Raises FreezeError (rule 4)."""
    url = saber_feed.SABER_URLS[group].format(season=int(season))
    resp = fetch(url)
    at = now()
    if resp.status != 200:
        raise FreezeError(f"{season} {group}: HTTP {resp.status} from {url}")
    try:
        splits = saber_feed.parse_splits(resp.body)
    except (ValueError, AttributeError, TypeError, IndexError) as exc:
        raise FreezeError(f"{season} {group}: unparseable body ({type(exc).__name__})") from exc
    n = len(splits)
    if n == 0 and int(season) < FEED_FIRST_SEASON:
        return absent_group(season, group, url, at, resp)
    if n >= saber_feed.SABER_LIMIT:
        raise FreezeError(f"{season} {group}: {n} rows reaches the feed's cap "
                          f"{saber_feed.SABER_LIMIT}; the response may be truncated")
    if n == 0:
        raise FreezeError(f"{season} {group}: the feed returned no rows")
    if n < MIN_ROWS:
        raise FreezeError(f"{season} {group}: {n} rows is under MIN_ROWS {MIN_ROWS} "
                          "(a partial response)")
    laid = group_rows(splits, group)
    block = {
        "group": group, "status": "frozen", "url": url, "fetched_at": at,
        "http_status": resp.status, "raw_sha256": hashlib.sha256(resp.body).hexdigest(),
        "n_rows": n, "n_players": len(laid["rows"]), "n_multi_team": laid["n_multi_team"],
        "ambiguous_ids": laid["ambiguous_ids"], "n_string_refused": laid["n_string_refused"],
        "fields": list(FIELDS[group]), "rows": laid["rows"],
    }
    block["content_sha256"] = group_content_sha(block)
    return block


def absent_group(season: int, group: str, url: str, at: str, resp: FetchResponse) -> dict:
    """A pre-2011 group the feed answered with HTTP 200 and no rows (rule 6)."""
    text = resp.body.decode("utf-8", errors="replace")
    block = {
        "group": group, "status": "absent", "url": url, "fetched_at": at,
        "http_status": resp.status, "raw_sha256": hashlib.sha256(resp.body).hexdigest(),
        "response": text[:ABSENT_BODY_MAX],
        "response_truncated": len(text) > ABSENT_BODY_MAX,
        "n_rows": 0, "n_players": 0, "n_multi_team": 0, "ambiguous_ids": [],
        "n_string_refused": 0, "fields": list(FIELDS[group]), "rows": {},
    }
    block["content_sha256"] = group_content_sha(block)
    return block


def _call_order(season: int) -> tuple[str, ...]:
    """Pitching first before 2011, so the first pre-2011 call is the probe."""
    if int(season) < FEED_FIRST_SEASON:
        return ("pitching", "hitting")
    return GROUPS


def empty_vintage() -> dict:
    return {"schema": SCHEMA, "vintage_id": "",
            "source": ("MLB StatsAPI stats=sabermetrics, FanGraphs' WAR line as MLB "
                       "publishes it; frozen per season, never refetched"),
            "urls": dict(saber_feed.SABER_URLS),
            "fields": {g: list(FIELDS[g]) for g in GROUPS},
            "builder": BUILD_CMD.split(" --")[0],
            "seasons": {}}


def freeze_seasons(existing: dict | None, seasons, *,
                   fetch: Callable[[str], FetchResponse] = http_fetch,
                   today: _dt.date | None = None,
                   now: Callable[[], str] | None = None,
                   refreeze: bool = False,
                   pause: Callable[[float], None] = time.sleep) -> dict:
    """Freeze `seasons` into a copy of `existing` and return the new vintage.

    Refuses (FreezeError, nothing returned) when any season is frozen already
    and `refreeze` is False, when any season is incomplete, or when any call
    fails rule 4. The caller writes the result with `write`."""
    today = today or _dt.date.today()
    now = now or (lambda: _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    want = sorted({int(s) for s in seasons})
    if not want:
        raise FreezeError("no season named")
    blob = json.loads(json.dumps(existing)) if existing else empty_vintage()
    frozen = sorted(int(s) for s in (blob.get("seasons") or {}))
    clash = [s for s in want if s in frozen]
    if clash and not refreeze:
        raise FreezeError(f"seasons already frozen and never overwritten: {clash} "
                          "(--refreeze is the only way past this, and this program never uses it)")
    bad = [(s, why) for s in want for ok, why in [season_complete(s, today)] if not ok]
    if bad:
        raise FreezeError("refused: " + "; ".join(why for _, why in bad))
    new_seasons: dict[str, dict] = {}
    first = True
    for s in want:
        sb: dict = {}
        for g in _call_order(s):
            if not first:
                pause(CALL_PAUSE_SECONDS)
            first = False
            sb[g] = freeze_group(s, g, fetch, now)
        sb["fetched_at"] = max(sb[g]["fetched_at"] for g in GROUPS)
        sb["basis"] = season_basis(sb)
        sb["content_sha256"] = season_content_sha(sb)
        new_seasons[str(s)] = sb
    blob.setdefault("seasons", {}).update(new_seasons)
    blob["seasons"] = {k: blob["seasons"][k] for k in sorted(blob["seasons"], key=int)}
    blob["vintage_id"] = vintage_id(blob)
    return blob


def season_basis(season_block: dict) -> str:
    """'fwar' when every group of the season is frozen, 'absent' when none
    is, else 'mixed' (rule 6)."""
    n = sum((season_block.get(g) or {}).get("status") == "frozen" for g in GROUPS)
    return "fwar" if n == len(GROUPS) else ("absent" if n == 0 else "mixed")


def verify(blob: dict) -> list[str]:
    """Every stored hash and the vintage_id recomputed; [] when all agree."""
    probs: list[str] = []
    if blob.get("schema") != SCHEMA:
        probs.append(f"schema {blob.get('schema')!r} is not {SCHEMA!r}")
    for s, sb in (blob.get("seasons") or {}).items():
        for g in GROUPS:
            gb = sb.get(g) or {}
            if gb.get("content_sha256") != group_content_sha(gb):
                probs.append(f"{s} {g}: content_sha256 does not match its rows")
        if sb.get("content_sha256") != season_content_sha(sb):
            probs.append(f"{s}: season content_sha256 does not match its groups")
    if blob.get("vintage_id") != vintage_id(blob):
        probs.append("vintage_id does not match the seasons it names")
    return probs


def write(blob: dict, path: Path | None = None) -> Path:
    """Atomic write (sibling temp + os.replace), compact JSON, one newline."""
    p = Path(path or VINTAGE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    text = json.dumps(blob, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    with open(tmp, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

_CACHE: dict | None = None


def available() -> bool:
    """True when the vintage can serve: a memoised payload (the test seam) or
    the file on disk."""
    return _CACHE is not None or VINTAGE_PATH.exists()


def load(path: Path | None = None) -> dict:
    """Read data/fwar_vintage.json (memoised; a `path` read is not memoised)."""
    global _CACHE
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if _CACHE is None:
        _CACHE = json.loads(VINTAGE_PATH.read_text(encoding="utf-8"))
    return _CACHE


def fwar_seasons(blob: dict | None = None) -> list[int]:
    """Seasons whose every group is frozen: the seasons fWAR serves."""
    blob = load() if blob is None else blob
    return sorted(int(s) for s, sb in (blob.get("seasons") or {}).items()
                  if season_basis(sb) == "fwar")


def mixed_seasons(blob: dict | None = None) -> list[int]:
    """Seasons recorded in the vintage with a group not frozen (pre-2011
    pitching absent): their consumers stamp `war_basis: mixed`."""
    blob = load() if blob is None else blob
    return sorted(int(s) for s, sb in (blob.get("seasons") or {}).items()
                  if season_basis(sb) != "fwar")


def war_basis(seasons, blob: dict | None = None) -> str:
    """The stamp for a cohort whose label reads `seasons`: 'fwar' only when
    every one of them is an fwar season of the vintage, else 'mixed' (rule 6;
    gate part 4.1 note 3). A season the vintage never recorded is not fwar."""
    blob = load() if blob is None else blob
    ok = set(fwar_seasons(blob))
    return "fwar" if all(int(s) in ok for s in seasons) else "mixed"


def war_by_group(blob: dict, season: int, group: str) -> dict[int, float]:
    """{mlbam: war} for one frozen (season, group); {} when not frozen."""
    gb = ((blob.get("seasons") or {}).get(str(int(season))) or {}).get(group) or {}
    if gb.get("status") != "frozen":
        return {}
    i = list(gb.get("fields") or []).index("war")
    out: dict[int, float] = {}
    for mid, vals in (gb.get("rows") or {}).items():
        v = vals[i]
        if v is not None:
            out[int(mid)] = float(v)
    return out


def side_targets(blob: dict | None, side: str) -> dict[tuple[int, int], float]:
    """{(mlbam, season): published war} for one war_source side ('bat' ->
    hitting, 'pit' -> pitching), over fwar_seasons only."""
    blob = load() if blob is None else blob
    group = SIDE_GROUP[side]
    out: dict[tuple[int, int], float] = {}
    for s in fwar_seasons(blob):
        for mid, w in war_by_group(blob, s, group).items():
            out[(mid, s)] = w
    return out


def season_totals(blob: dict | None = None) -> dict[tuple[int, int], float]:
    """{(mlbam, season): hitting war + pitching war} over fwar_seasons, for
    every player with a row in at least one group (the bWAR aggregate's
    two-frame summing rule)."""
    blob = load() if blob is None else blob
    out: dict[tuple[int, int], float] = {}
    for s in fwar_seasons(blob):
        for g in GROUPS:
            for mid, w in war_by_group(blob, s, g).items():
                out[(mid, s)] = out.get((mid, s), 0.0) + w
    return out


def field_presence(blob: dict) -> dict[str, dict[str, dict]]:
    """{season: {group: {"n_rows": n, "share": {field: share of rows with a
    non-null value}}}} (4dp), the schema receipt the orchestrator asked for."""
    out: dict[str, dict[str, dict]] = {}
    for s, sb in (blob.get("seasons") or {}).items():
        for g in GROUPS:
            gb = sb.get(g) or {}
            rows = list((gb.get("rows") or {}).values())
            fields = list(gb.get("fields") or [])
            n = len(rows)
            share = {f: (round(sum(1 for r in rows if r[i] is not None) / n, 4) if n else None)
                     for i, f in enumerate(fields)}
            out.setdefault(s, {})[g] = {"status": gb.get("status"), "n_rows": n, "share": share}
    return out
