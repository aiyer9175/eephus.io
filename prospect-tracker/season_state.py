# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""season_state.py - the site's one season state (site pass SP-D5, PROSPX_4_SEASON_STATE).

WHY THIS EXISTS (2026-10-08). Each module decided "is the season over" on its own
(dfs.js season_over, the FA tracker's "preseason", the PROSPX Hot chip, the
Leaderboards window chips, the Standout ribbon), so in October the site read as
live in some places and finished in others. One object, written here every night
from the StatsAPI season calendar, now answers it for every page; each consumer
keeps its own old default when the object is absent.

THE BOOT FILE (the choice the spec asked to document). The object rides in
assets/eephus-config.js, between the two marker lines below. Of the scripts every
page loads (31 of 31 served pages: eephus-config.js, eephus-account.js,
eephus-ui.js, eephus-bg.js, eephus-gl.js, eephus-export.js, eephus-nav.js), it is
the smallest (1,436 bytes before the block), it is deferred ahead of
eephus-ui.js in document order on every page, and /assets/ is served no-cache, so
no page needs a new request or a fetch. Only the marked block is rewritten; the
deploy-time Supabase and analytics values above it are never read or touched.

THE FIELDS.
  phase               spring | regular | postseason | offseason on the build date
  season              the season of record: the newest MLB season whose regular
                      season has begun on or before the build date
  mlb_regular_end     that season's regularSeasonEndDate (StatsAPI /seasons, sportId 1)
  mlb_postseason_end  the date of the World Series' deciding game once the schedule
                      shows one, else the calendar's postSeasonEndDate
  milb_last_game      the latest regularSeasonEndDate over the four full-season
                      MiLB levels (sportId 11 to 14)
  next_opening_day    the first regularSeasonStartDate after the build date
  draft_date          the season of record's MLB Draft opening day: two days before
                      its All-Star Game (the Draft has opened on the Sunday of
                      All-Star week every year since 2021)
  j2_open             January 15 after the season of record (the international
                      amateur signing period opens January 15)
  posting_window      [November 1, December 15] of the season of record (the NPB
                      posting window)

No build stamp rides in the block, so it changes only when a date or the phase
does (a handful of nights a year) and the stamped pages do not churn nightly.

Only the dates above are written; nothing here is a model output or a served
number.

CLI:
    python season_state.py                  # compute for today and write the block
    python season_state.py --dry-run        # print the object, write nothing
    python season_state.py --date 2026-12-01 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger("season_state")

ROOT = Path(__file__).resolve().parent
BOOT_PATH = ROOT / "assets" / "eephus-config.js"

MILB_SPORT_IDS = (11, 12, 13, 14)
PHASES = ("spring", "regular", "postseason", "offseason")
FIELDS = ("phase", "season", "mlb_regular_end", "mlb_postseason_end", "milb_last_game",
          "next_opening_day", "draft_date", "j2_open", "posting_window")

BLOCK_BEGIN = "// season-state:begin (season_state.py writes this block every night; do not edit)"
BLOCK_END = "// season-state:end"
_BLOCK_RE = re.compile(re.escape(BLOCK_BEGIN) + r".*?" + re.escape(BLOCK_END), re.S)

WS_TTL = 6 * 3600


def _iso(v) -> str | None:
    s = str(v or "")[:10]
    try:
        date.fromisoformat(s)
    except ValueError:
        return None
    return s


def build_state(today: date, mlb: dict, milb: dict | None = None,
                ws_end: str | None = None) -> dict:
    """The season state on `today`, from calendar rows only (pure).

    mlb   {season: StatsAPI /seasons row for sportId 1}
    milb  {season: [the /seasons rows for sportId 11 to 14]}
    ws_end the World Series' deciding-game date for the season of record, if known
    """
    t = today.isoformat()
    rows = {int(s): r for s, r in (mlb or {}).items() if r and _iso(r.get("regularSeasonStartDate"))}
    begun = [s for s, r in rows.items() if _iso(r["regularSeasonStartDate"]) <= t]
    season = max(begun) if begun else (min(rows) - 1 if rows else today.year - 1)
    cur = rows.get(season) or {}
    nxt = rows.get(season + 1) or {}

    reg_end = _iso(cur.get("regularSeasonEndDate"))
    post_end = _iso(ws_end) or _iso(cur.get("postSeasonEndDate"))
    spring_next = _iso(nxt.get("springStartDate"))
    if reg_end and t <= reg_end:
        phase = "regular"
    elif post_end and t <= post_end:
        phase = "postseason"
    elif spring_next and t >= spring_next:
        phase = "spring"
    else:
        phase = "offseason"

    starts = sorted(_iso(r.get("regularSeasonStartDate")) for r in rows.values())
    next_open = next((s for s in starts if s and s > t), None)

    ends = [_iso(r.get("regularSeasonEndDate")) for r in ((milb or {}).get(season) or []) if r]
    ends = [e for e in ends if e]

    asg = _iso(cur.get("allStarDate"))
    draft = (date.fromisoformat(asg) - timedelta(days=2)).isoformat() if asg else None

    return {
        "phase": phase,
        "season": season,
        "mlb_regular_end": reg_end,
        "mlb_postseason_end": post_end,
        "milb_last_game": max(ends) if ends else None,
        "next_opening_day": next_open,
        "draft_date": draft,
        "j2_open": f"{season + 1}-01-15",
        "posting_window": [f"{season}-11-01", f"{season}-12-15"],
    }


# ---------------------------------------------------------------------------
# the StatsAPI reads (the one cache the fantasy calendar already keeps)
# ---------------------------------------------------------------------------

def _seasons_row(season: int, sport_id: int, use_cache: bool = True) -> dict | None:
    """One /seasons row. sportId 1 shares fantasy_schedule's own cache file, so the
    futures stamp and this state read the same calendar."""
    import fantasy_schedule as fs
    name = f"season_{int(season)}.json" if sport_id == 1 else f"season_{int(season)}_sport{sport_id}.json"
    path = fs.CACHE_DIR / name
    try:
        data = fs._cached_get(path, fs.SEASONS_API + str(int(season)), {"sportId": sport_id},
                              fs.SEASONS_TTL, use_cache)
    except Exception:                                          # noqa: BLE001
        log.warning("season_state: /seasons fetch failed for %s sport %s", season, sport_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    for row in (data or {}).get("seasons") or []:
        if str((row or {}).get("seasonId")) == str(int(season)):
            return row
    return None


def world_series_end(season: int, use_cache: bool = True) -> str | None:
    """The officialDate of the game that gave a club its fourth World Series win,
    or None while the series is undecided or unreadable."""
    import fantasy_schedule as fs
    path = fs.CACHE_DIR / f"world_series_{int(season)}.json"
    try:
        data = fs._cached_get(path, fs.SCHEDULE_API,
                              {"sportId": 1, "season": int(season), "gameType": "W"},
                              WS_TTL, use_cache)
    except Exception:                                          # noqa: BLE001
        return None
    wins: dict = {}
    for d in (data or {}).get("dates") or []:
        for g in d.get("games") or []:
            if ((g.get("status") or {}).get("abstractGameState")) != "Final":
                continue
            for side in ("home", "away"):
                team = ((g.get("teams") or {}).get(side)) or {}
                if team.get("isWinner"):
                    tid = (team.get("team") or {}).get("id")
                    wins[tid] = wins.get(tid, 0) + 1
                    if wins[tid] >= 4:
                        return _iso(g.get("officialDate") or d.get("date"))
    return None


def compute(today: date | None = None, use_cache: bool = True) -> dict:
    today = today or date.today()
    mlb = {}
    for y in (today.year - 1, today.year, today.year + 1):
        row = _seasons_row(y, 1, use_cache)
        if row:
            mlb[y] = row
    probe = build_state(today, mlb)
    season = probe["season"]
    milb = {season: [r for r in (_seasons_row(season, sid, use_cache) for sid in MILB_SPORT_IDS) if r]}
    ws = None
    cur = mlb.get(season) or {}
    reg_end, post_end = _iso(cur.get("regularSeasonEndDate")), _iso(cur.get("postSeasonEndDate"))
    if reg_end and post_end and reg_end < today.isoformat() <= post_end:
        ws = world_series_end(season, use_cache)
    return build_state(today, mlb, milb, ws)


# ---------------------------------------------------------------------------
# the boot block
# ---------------------------------------------------------------------------

def render_block(state: dict) -> str:
    body = json.dumps({k: state.get(k) for k in FIELDS}, separators=(", ", ": "))
    return f"{BLOCK_BEGIN}\nwindow.EEPHUS_SEASON = {body};\n{BLOCK_END}"


def read_boot(path: Path | None = None) -> dict | None:
    """The object the boot block carries, or None."""
    try:
        text = Path(path or BOOT_PATH).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"window\.EEPHUS_SEASON = (\{.*?\});", text)
    if not m or BLOCK_BEGIN not in text:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def write_boot(state: dict, path: Path | None = None) -> bool:
    """Replace the marked block (append it when absent), keeping the file's own
    line endings and every other byte. Returns True when the file changed."""
    path = Path(path or BOOT_PATH)
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    block = render_block(state).replace("\n", nl)
    if _BLOCK_RE.search(raw):
        new = _BLOCK_RE.sub(lambda _m: block, raw, count=1)
    else:
        new = raw.rstrip("\r\n") + nl + nl + block + nl
    if new == raw:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="build date, YYYY-MM-DD (default today)")
    ap.add_argument("--dry-run", action="store_true", help="print the object, write nothing")
    ap.add_argument("--no-cache", action="store_true", help="refetch the calendar")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.date) if a.date else None
    state = compute(today, use_cache=not a.no_cache)
    print(json.dumps(state, indent=1))
    if not a.dry_run:
        print("written" if write_boot(state) else "unchanged", BOOT_PATH)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
