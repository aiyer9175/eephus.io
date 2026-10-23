#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fetch_milb_feeds_hist - the minor-league game feeds the runner record's history
partition reads for 2021 and 2022 at every level and 2023 at High-A, Double-A and
Triple-A (owner answer ETOOLS-SPD-EBR, 2026-10-21, "Backfill 2021-2023";
docs/tools-2026-10/ETOOLS_AMENDMENT_5.md section 9 names the seasons).

WHAT IT WRITES. The /feed/live payload of every FINAL regular-season game the
league schedule lists for each unit (level, season) of ``HIST_UNITS`` into
``.cache/milb_feeds_hist/feeds/<game_pk>.json``, and NEVER into
``.cache/game_feeds`` (the live feed cache, read by other modules and pruned at
400 days), ``.cache/pbp_runners`` (the record, written only by
tools/build_runner_moves.py), ``.cache/win_prob``, ``.cache/win_prob_hist`` or
``.cache/pbp_corpus``. The schedule each unit was fetched against is kept under
``schedule/<level>_<season>.json``.

THE PATTERN OF tools/fetch_win_prob_hist.py (the eBR history backfill), whose
receipts healer, pacer and User-Agent it imports unchanged:

POLITE. At least ``MIN_INTERVAL`` seconds between requests, measured from the
previous request's start (two a second at most; the minor-league fill of
tools/build_ebr_milb.py used 0.2 s), the house User-Agent, one payload at a time,
no workers. The run stops itself, resumable, inside the nightly fetch window
(06:00 to 11:00 UTC), which belongs to the nightly job.

RESUMABLE AND FAIL-SOFT. A payload on disk that an ok receipt names, whose bytes
hash to that receipt and that reads as a final game with a completed last play is
skipped; a partial, unreadable, unreceipted or altered one is fetched again. A
receipts file an unclean shutdown damaged is healed first (lines that parse are
kept, the damaged file parked as ``receipts.jsonl.damaged-<stamp>``). A 404 is
recorded as ``no_play``; any other failure as ``error`` (retried by the next run);
a payload that is not a final game with its plays as ``partial``.

RECEIPTS. ``receipts.jsonl`` gains one line per request: game_pk, level, season,
the official date, fetched_at (UTC), bytes, the sha256 of the bytes written, the
status and the elapsed milliseconds. ``summary.json`` holds the per-unit counts of
the last run; ``fetch.log`` the log.

Run (outside any pipeline run; about 26,800 games, 16 GB, four hours):
    python tools/fetch_milb_feeds_hist.py [--units aaa|2021,...] [--limit N]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

_log = logging.getLogger("fetch_milb_feeds_hist")

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
for _p in (str(TOOLS), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.append(_p)

import fetch_win_prob_hist as fwh  # noqa: E402  the pattern: heal_receipts, Pacer, the User-Agent

#: sportId of each partition (tools/build_runner_moves.MILB_LEVELS, inverted).
LEVEL_SPORT = {"aaa": 11, "aa": 12, "high_a": 13, "single_a": 14, "rookie": 16}
#: The units the owner named: 2021 and 2022 at every level, 2023 at High-A to Triple-A
#: (Rookie and Single-A 2023 are already in the record from .cache/game_feeds).
HIST_UNITS: tuple[tuple[str, int], ...] = tuple(
    [(lv, s) for s in (2021, 2022) for lv in ("aaa", "aa", "high_a", "single_a", "rookie")]
    + [(lv, 2023) for lv in ("aaa", "aa", "high_a")])
HIST_SEASONS: tuple[int, ...] = tuple(sorted({s for _, s in HIST_UNITS}))
HIST_DIR = REPO_ROOT / ".cache" / "milb_feeds_hist"
FEEDS_SUBDIR = "feeds"
#: Directories a history payload must never land in.
FORBIDDEN_DIR_NAMES = ("game_feeds", "pbp_runners", "win_prob", "win_prob_hist", "pbp_corpus")
MIN_INTERVAL = 0.5
TIMEOUT = 90
NO_PLAY_STATUS = 404
#: The nightly job's fetch window (UTC hours, start inclusive, end exclusive).
NIGHTLY_WINDOW_UTC = (6, 11)
LIVE_FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId={sport}&season={season}&gameType=R"
            "&startDate={season}-01-01&endDate={season}-12-31")


def check_out_dir(out_dir: Path) -> Path:
    """Refuse the live feed cache, the record, the winProbability caches and the corpus."""
    out_dir = Path(out_dir)
    resolved = out_dir.resolve()
    for part in resolved.parts + (out_dir.name,):
        if part in FORBIDDEN_DIR_NAMES:
            raise RuntimeError(f"refusing to write minor-league history payloads under {part}: {out_dir}")
    return out_dir


def unit_key(unit) -> str:
    return f"{unit[0]}|{int(unit[1])}"


def in_nightly_window(now: _dt.datetime | None = None) -> bool:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return NIGHTLY_WINDOW_UTC[0] <= now.astimezone(_dt.timezone.utc).hour < NIGHTLY_WINDOW_UTC[1]


def feed_complete(data, pk: int | None = None) -> bool:
    """A final game's feed: the status Final, the game_pk as asked and a non-empty
    play list. The last play is not required to be complete: a game called early
    (rain, wet grounds) ends on an open 'Game Advisory' play and is final as it
    stands, and the walk reads it as the record's other minor-league games are read."""
    if not isinstance(data, dict):
        return False
    gd = data.get("gameData") or {}
    if ((gd.get("status") or {}).get("abstractGameState")) != "Final":
        return False
    if pk is not None and int((gd.get("game") or {}).get("pk") or -1) != int(pk):
        return False
    plays = ((data.get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    return bool(plays)


def payload_complete(path: Path, sha256: str | None = None, pk: int | None = None) -> bool:
    try:
        body = Path(path).read_bytes()
        data = json.loads(body)
    except (OSError, ValueError):
        return False
    if sha256 is not None and hashlib.sha256(body).hexdigest() != sha256:
        return False
    return feed_complete(data, pk)


def unit_schedule(unit, out_dir: Path, *, session, pacer, user_agent: str) -> list:
    """[[game_pk, official_date], ...] of the unit's FINAL regular-season games, sorted
    by game_pk and kept under schedule/<level>_<season>.json (fetched once)."""
    lv, season = unit[0], int(unit[1])
    p = Path(out_dir) / "schedule" / f"{lv}_{season}.json"
    if p.exists():
        try:
            return [[int(a), b] for a, b in json.loads(p.read_text(encoding="utf-8"))]
        except (ValueError, TypeError):
            pass
    pacer.wait()
    resp = session.get(SCHEDULE.format(sport=LEVEL_SPORT[lv], season=season),
                       headers={"User-Agent": user_agent}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"schedule {lv} {season}: HTTP {resp.status_code}")
    d = json.loads(resp.content)
    games = {}
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            if ((g.get("status") or {}).get("abstractGameState")) == "Final" and (g.get("gameType") or "R") == "R":
                games[int(g["gamePk"])] = g.get("officialDate") or day.get("date")
    out = [[pk, games[pk]] for pk in sorted(games)]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)
    return out


def fetch_one(pk: int, *, session, feeds_dir: Path, pacer, user_agent: str) -> dict:
    """Fetch one payload into feeds_dir/<pk>.json (atomic). Returns the receipt fields:
    status in {ok, partial, no_play, error}, bytes, sha256, elapsed_ms."""
    pacer.wait()
    t0 = time.monotonic()
    try:
        resp = session.get(LIVE_FEED.format(pk=int(pk)), headers={"User-Agent": user_agent}, timeout=TIMEOUT)
    except Exception as e:  # noqa: BLE001 - fail-soft: the next run retries
        return {"status": "error", "bytes": 0, "sha256": None,
                "elapsed_ms": int((time.monotonic() - t0) * 1000), "error": str(e)[:200]}
    elapsed = int((time.monotonic() - t0) * 1000)
    if resp.status_code == NO_PLAY_STATUS:
        return {"status": "no_play", "bytes": 0, "sha256": None, "elapsed_ms": elapsed, "http": NO_PLAY_STATUS}
    if resp.status_code != 200:
        return {"status": "error", "bytes": 0, "sha256": None, "elapsed_ms": elapsed,
                "http": int(resp.status_code)}
    body = resp.content
    try:
        data = json.loads(body)
    except ValueError:
        return {"status": "error", "bytes": len(body), "sha256": None, "elapsed_ms": elapsed,
                "error": "not json"}
    if not feed_complete(data, pk):
        d = data if isinstance(data, dict) else {}
        st = (d.get("gameData") or {}).get("status") or {}
        plays = ((d.get("liveData") or {}).get("plays") or {}).get("allPlays")
        if st.get("abstractGameState") == "Final" and not plays:
            # a game the schedule lists as final that was never played (Cancelled: Rain)
            return {"status": "no_play", "bytes": 0, "sha256": None, "elapsed_ms": elapsed,
                    "reason": str(st.get("detailedState") or "")[:80]}
        return {"status": "partial", "bytes": len(body), "sha256": None, "elapsed_ms": elapsed}
    path = Path(feeds_dir) / f"{int(pk)}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
    return {"status": "ok", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "elapsed_ms": elapsed}


def unit_status(out_dir: Path, units=HIST_UNITS) -> dict:
    """{unit_key: {"scheduled", "present", "no_play", "complete"}} from the kept
    schedules, the ok receipts and the payloads on disk (no network): a unit is
    complete when every listed game is on disk under its ok receipt or answered 404."""
    out_dir = Path(out_dir)
    ok, no_play = {}, set()
    rp = out_dir / "receipts.jsonl"
    if rp.exists():
        for line in rp.read_bytes().split(b"\n"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "ok":
                ok[int(r["game_pk"])] = r.get("sha256")
                no_play.discard(int(r["game_pk"]))
            elif r.get("status") == "no_play":
                no_play.add(int(r["game_pk"]))
    res = {}
    for u in units:
        p = out_dir / "schedule" / f"{u[0]}_{int(u[1])}.json"
        if not p.exists():
            res[unit_key(u)] = {"scheduled": None, "present": 0, "no_play": 0, "complete": False}
            continue
        games = [int(a) for a, _ in json.loads(p.read_text(encoding="utf-8"))]
        present = sum(1 for pk in games if pk in ok and (out_dir / FEEDS_SUBDIR / f"{pk}.json").exists())
        nop = sum(1 for pk in games if pk in no_play and pk not in ok)
        res[unit_key(u)] = {"scheduled": len(games), "present": present, "no_play": nop,
                            "complete": present + nop >= len(games)}
    return res


def run(units=HIST_UNITS, *, out_dir: Path = HIST_DIR, session=None, pacer=None,
        user_agent: str | None = None, limit: int | None = None, schedules: dict | None = None,
        now=None) -> dict:
    """Fetch every listed game of each unit not already complete on disk. Returns the
    per-unit summary, also written to out_dir/summary.json. ``now`` (a callable giving
    an aware UTC datetime) is the clock the nightly-window stop reads."""
    out_dir = check_out_dir(out_dir)
    feeds_dir = out_dir / FEEDS_SUBDIR
    feeds_dir.mkdir(parents=True, exist_ok=True)
    if session is None:
        import feed_cache
        session = feed_cache.SESSION
    pacer = pacer or fwh.Pacer(MIN_INTERVAL)
    ua = user_agent or fwh.house_user_agent()
    clock = now or (lambda: _dt.datetime.now(_dt.timezone.utc))
    receipts = out_dir / "receipts.jsonl"
    ok_receipts = fwh.heal_receipts(out_dir)
    summary: dict = {"started_at": fwh._now_iso(), "out_dir": str(out_dir), "user_agent": ua,
                     "min_interval_s": pacer.interval, "ok_receipts_before": len(ok_receipts),
                     "units": {}, "stopped": None}
    n_requests = 0
    for unit in units:
        lv, season = unit[0], int(unit[1])
        key = unit_key(unit)
        if in_nightly_window(clock()):
            summary["stopped"] = "nightly fetch window"
            break
        games = (schedules or {}).get(key) if schedules is not None else None
        if games is None:
            games = unit_schedule(unit, out_dir, session=session, pacer=pacer, user_agent=ua)
        blk = {"scheduled": len(games), "present_before": 0, "fetched": 0, "no_play": 0,
               "partial": 0, "error": 0, "bytes": 0}
        _log.info("%s: %d final regular-season games listed", key, len(games))
        for pk, date in games:
            pk = int(pk)
            path = feeds_dir / f"{pk}.json"
            if pk in ok_receipts and path.exists() and payload_complete(path, ok_receipts[pk], pk):
                blk["present_before"] += 1
                continue
            if limit is not None and n_requests >= limit:
                continue
            if summary["stopped"] or in_nightly_window(clock()):
                summary["stopped"] = "nightly fetch window"
                continue
            n_requests += 1
            rec = fetch_one(pk, session=session, feeds_dir=feeds_dir, pacer=pacer, user_agent=ua)
            rec.update({"game_pk": pk, "level": lv, "season": season, "date": date,
                        "fetched_at": fwh._now_iso()})
            with open(receipts, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
            st = rec["status"]
            if st == "ok":
                ok_receipts[pk] = rec["sha256"]
            blk["fetched" if st == "ok" else st] += 1
            blk["bytes"] += int(rec.get("bytes") or 0)
            if st != "ok":
                _log.warning("%s %s: %s %s", key, pk, st, rec.get("http") or rec.get("error") or "")
            elif n_requests % 250 == 0:
                _log.info("%s: %d fetched this run (%d requests)", key, blk["fetched"], n_requests)
        present = sum(1 for pk, _ in games if (feeds_dir / f"{int(pk)}.json").exists())
        blk["present_after"] = present
        blk["complete"] = bool(present + blk["no_play"] >= len(games))
        summary["units"][key] = blk
        _log.info("%s: present %d/%d  fetched %d  no_play %d  partial %d  error %d  %.1f MB",
                  key, present, len(games), blk["fetched"], blk["no_play"], blk["partial"],
                  blk["error"], blk["bytes"] / 1e6)
    summary["finished_at"] = fwh._now_iso()
    summary["requests"] = n_requests
    tmp = out_dir / "summary.json.tmp"
    tmp.write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(out_dir / "summary.json")
    return summary


def _parse_units(s: str | None) -> list:
    if not s:
        return list(HIST_UNITS)
    out = []
    for part in s.split(","):
        lv, yr = part.strip().split("|")
        u = (lv, int(yr))
        if u not in HIST_UNITS:
            raise SystemExit(f"history units are {[unit_key(x) for x in HIST_UNITS]}; refusing {part}")
        out.append(u)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--units", default=None, help="level|season,... (default: every history unit)")
    ap.add_argument("--limit", type=int, default=None, help="at most N payload requests this run")
    ap.add_argument("--status", action="store_true", help="print the per-unit completeness and exit")
    a = ap.parse_args(argv)
    out_dir = check_out_dir(HIST_DIR)
    if a.status:
        for k, v in unit_status(out_dir).items():
            print(k, v)
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(out_dir / "fetch.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    t0 = time.time()
    summ = run(_parse_units(a.units), out_dir=out_dir, limit=a.limit)
    tot = sum(b["fetched"] for b in summ["units"].values())
    mb = sum(b["bytes"] for b in summ["units"].values()) / 1e6
    print(f"done: {tot} payloads, {mb:.1f} MB, {summ['requests']} requests in {time.time() - t0:.0f} s"
          + (f"; stopped: {summ['stopped']}" if summ["stopped"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
