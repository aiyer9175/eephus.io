#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fetch_win_prob_hist - the history play-by-play eBR's runner record reads for
2011 to 2017 and 2020 (docs/ebr-2026-09-30/EBR_GATE.md part 2.1; owner answer
EBR-Q4 (b), 2026-10-01).

WHAT IT WRITES. The winProbability payload of every FINAL regular-season game
(``mlb_leverage.season_game_pks(season, game_type="R")``) of the history seasons
into ``.cache/win_prob_hist/<game_pk>.json``, and NEVER into ``.cache/win_prob/``:
the play-by-play corpus (tools/build_pbp_corpus.py) globs that directory and the
win-expectancy table pools every season the corpus holds, so a history payload
there would move registered tables. The schedule each season was fetched against
is kept under ``schedule/<season>.json`` beside the payloads.

POLITE. At least ``MIN_INTERVAL`` seconds between requests (one request a
second at most), the house User-Agent (pipeline_vintage.USER_AGENT), one payload
at a time, no workers.

RESUMABLE AND FAIL-SOFT. A payload already on disk whose play list ends the game
(``mlb_leverage.plays_end_the_game``), that an ok receipt names and whose bytes
hash to that receipt's sha256 is skipped; a partial, unreadable, unreceipted or
altered one is fetched again. A receipts file an unclean shutdown damaged (NUL
runs, a cut line) is healed before anything is fetched: the lines that parse are
kept, the damaged file is parked beside it as ``receipts.jsonl.damaged-<stamp>``
(the 2026-10-14 blue screens zero-filled files mid-write; receipts were lost for
payloads on disk, and payloads were zero-filled under ok receipts). A game the
endpoint answers 404 for (a game the schedule lists
as final but that was never played: cancelled, or postponed and never made up)
is recorded as ``no_play`` and the run continues; any other failure is recorded
as ``error`` and the next run retries it. Nothing aborts the run but a refused
output directory.

RECEIPTS. ``receipts.jsonl`` gains one line per request: game_pk, season, the
official date, fetched_at (UTC), the byte count, the sha256 of the bytes
written, the status and the request's elapsed milliseconds. ``summary.json``
holds the per-season counts of the last run. ``fetch.log`` is the log.

Run (outside any pipeline run; about 17,900 games, 18 GB, five hours):
    python tools/fetch_win_prob_hist.py [--seasons 2011-2017,2020] [--limit N]
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

_log = logging.getLogger("fetch_win_prob_hist")

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))         # mlb_leverage, feed_cache, pipeline_vintage

#: The seasons the history directory holds: eWAR's window before the record's
#: own seasons (2018 on), and the 60-game 2020 season.
HIST_SEASONS: tuple[int, ...] = (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2020)
HIST_DIR = REPO_ROOT / ".cache" / "win_prob_hist"
#: Directories a history payload must never land in.
FORBIDDEN_DIR_NAMES = ("win_prob", "pbp_corpus", "pbp_runners")
MIN_INTERVAL = 1.0
TIMEOUT = 60
NO_PLAY_STATUS = 404


def house_user_agent() -> str:
    """The identifying User-Agent every polite fetch of this repository sends."""
    try:
        from pipeline_vintage import USER_AGENT
        return USER_AGENT
    except Exception:  # noqa: BLE001 - the string, should the module ever move
        return "eephus.io-prospect-tracker/1.0 (+https://eephus.io; arkndjl@gmail.com)"


def check_out_dir(out_dir: Path) -> Path:
    """Refuse the live winProbability cache, the corpus and the record."""
    out_dir = Path(out_dir)
    import mlb_leverage
    resolved = out_dir.resolve()
    if resolved == Path(mlb_leverage.CACHE_DIR).resolve() or out_dir.name in FORBIDDEN_DIR_NAMES:
        raise RuntimeError(f"refusing to write history payloads into {out_dir}")
    for part in resolved.parts:
        if part in FORBIDDEN_DIR_NAMES:
            raise RuntimeError(f"refusing to write history payloads under {part}: {out_dir}")
    return out_dir


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def payload_complete(path: Path, sha256: str | None = None) -> bool:
    """True when the payload on disk parses, its play list ends the game and,
    when a receipt's sha256 is given, its bytes hash to it."""
    import mlb_leverage
    try:
        body = Path(path).read_bytes()
        data = json.loads(body)
    except (OSError, ValueError):
        return False
    if sha256 is not None and hashlib.sha256(body).hexdigest() != sha256:
        return False
    plays = data if isinstance(data, list) else ((data or {}).get("winProbability") or [])
    return bool(plays) and mlb_leverage.plays_end_the_game(plays)


def heal_receipts(out_dir: Path) -> dict:
    """{game_pk: sha256} of the ok receipts in out_dir/receipts.jsonl, the last
    line per game winning. A file an unclean shutdown damaged (NUL bytes, a line
    that does not parse) is parked as receipts.jsonl.damaged-<stamp> and
    rewritten with the lines that parse, so every later reader sees clean
    lines. Idempotent: a clean file is read and left alone."""
    receipts = Path(out_dir) / "receipts.jsonl"
    if not receipts.exists():
        return {}
    raw = receipts.read_bytes()
    kept, ok, damaged = [], {}, 0
    for line in raw.split(b"\n"):
        if not line.strip(b" \r\0"):
            damaged += int(b"\0" in line)
            continue
        try:
            r = json.loads(line)
        except ValueError:
            damaged += 1
            continue
        kept.append(line.rstrip(b"\r"))
        if r.get("status") == "ok":
            ok[int(r["game_pk"])] = r.get("sha256")
    if damaged:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        parked = receipts.with_name(f"receipts.jsonl.damaged-{stamp}")
        receipts.replace(parked)
        receipts.write_bytes(b"\n".join(kept) + (b"\n" if kept else b""))
        _log.warning("receipts healed: %d damaged line(s) dropped, %d kept, original parked as %s",
                     damaged, len(kept), parked.name)
    return ok


def season_schedule(season: int, out_dir: Path) -> list:
    """[[game_pk, official_date], ...]: EXACTLY mlb_leverage.season_game_pks(season,
    game_type="R"), sorted by game_pk and kept under schedule/<season>.json."""
    import mlb_leverage
    games = sorted((int(pk), d) for pk, d in mlb_leverage.season_game_pks(int(season), game_type="R"))
    p = Path(out_dir) / "schedule" / f"{int(season)}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([[pk, d] for pk, d in games], separators=(",", ":")), encoding="utf-8")
    return [[pk, d] for pk, d in games]


class Pacer:
    """At most one request per ``interval`` seconds, measured from the previous
    request's start."""

    def __init__(self, interval: float = MIN_INTERVAL, *, clock=time.monotonic, sleep=time.sleep):
        self.interval = float(interval)
        self.clock = clock
        self.sleep = sleep
        self.last: float | None = None

    def wait(self) -> None:
        if self.last is not None:
            gap = self.interval - (self.clock() - self.last)
            if gap > 0:
                self.sleep(gap)
        self.last = self.clock()


def fetch_one(pk: int, *, session, out_dir: Path, pacer: Pacer, user_agent: str) -> dict:
    """Fetch one payload into out_dir/<pk>.json (atomic). Returns the receipt
    fields: status in {ok, partial, no_play, error}, bytes, sha256, elapsed_ms."""
    import mlb_leverage
    url = f"{mlb_leverage.WP_API}/{int(pk)}/winProbability"
    pacer.wait()
    t0 = time.monotonic()
    try:
        resp = session.get(url, headers={"User-Agent": user_agent}, timeout=TIMEOUT)
    except Exception as e:  # noqa: BLE001 - fail-soft: the next run retries
        return {"status": "error", "bytes": 0, "sha256": None,
                "elapsed_ms": int((time.monotonic() - t0) * 1000), "error": str(e)[:200]}
    elapsed = int((time.monotonic() - t0) * 1000)
    if resp.status_code == NO_PLAY_STATUS:
        return {"status": "no_play", "bytes": 0, "sha256": None, "elapsed_ms": elapsed,
                "http": NO_PLAY_STATUS}
    if resp.status_code != 200:
        return {"status": "error", "bytes": 0, "sha256": None, "elapsed_ms": elapsed,
                "http": int(resp.status_code)}
    body = resp.content
    try:
        data = json.loads(body)
    except ValueError:
        return {"status": "error", "bytes": len(body), "sha256": None, "elapsed_ms": elapsed,
                "error": "not json"}
    plays = data if isinstance(data, list) else ((data or {}).get("winProbability") or [])
    if not plays or not mlb_leverage.plays_end_the_game(plays):
        return {"status": "partial", "bytes": len(body), "sha256": None, "elapsed_ms": elapsed,
                "plays": len(plays or ())}
    path = Path(out_dir) / f"{int(pk)}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
    return {"status": "ok", "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "elapsed_ms": elapsed, "plays": len(plays)}


def run(seasons=HIST_SEASONS, *, out_dir: Path = HIST_DIR, session=None, pacer: Pacer | None = None,
        user_agent: str | None = None, limit: int | None = None, schedules: dict | None = None) -> dict:
    """Fetch every listed game of each season not already complete on disk.
    Returns the per-season summary, also written to out_dir/summary.json."""
    out_dir = check_out_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if session is None:
        import feed_cache
        session = feed_cache.SESSION
    pacer = pacer or Pacer()
    ua = user_agent or house_user_agent()
    receipts = out_dir / "receipts.jsonl"
    ok_receipts = heal_receipts(out_dir)
    summary: dict = {"started_at": _now_iso(), "out_dir": str(out_dir), "user_agent": ua,
                     "min_interval_s": pacer.interval, "ok_receipts_before": len(ok_receipts),
                     "seasons": {}}
    n_requests = 0
    for season in seasons:
        season = int(season)
        games = (schedules or {}).get(season) if schedules is not None else None
        if games is None:
            games = season_schedule(season, out_dir)
        blk = {"scheduled": len(games), "present_before": 0, "fetched": 0, "no_play": 0,
               "partial": 0, "error": 0, "bytes": 0}
        _log.info("%s: %d final regular-season games listed", season, len(games))
        for pk, date in games:
            pk = int(pk)
            path = out_dir / f"{pk}.json"
            if pk in ok_receipts and path.exists() and payload_complete(path, ok_receipts[pk]):
                blk["present_before"] += 1
                continue
            if limit is not None and n_requests >= limit:
                continue
            n_requests += 1
            rec = fetch_one(pk, session=session, out_dir=out_dir, pacer=pacer, user_agent=ua)
            rec.update({"game_pk": pk, "season": season, "date": date, "fetched_at": _now_iso()})
            with open(receipts, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
            st = rec["status"]
            if st == "ok":
                ok_receipts[pk] = rec["sha256"]
            blk["fetched" if st == "ok" else st] += 1
            blk["bytes"] += int(rec.get("bytes") or 0)
            if st != "ok":
                _log.warning("%s %s: %s %s", season, pk, st, rec.get("http") or rec.get("error") or "")
            elif n_requests % 100 == 0:
                _log.info("%s: %d fetched this run (%d requests)", season, blk["fetched"], n_requests)
        present = sum(1 for pk, _ in games if (out_dir / f"{int(pk)}.json").exists())
        blk["present_after"] = present
        blk["complete"] = bool(present + blk["no_play"] >= len(games))
        summary["seasons"][str(season)] = blk
        _log.info("%s: present %d/%d  fetched %d  no_play %d  partial %d  error %d  %.1f MB",
                  season, present, len(games), blk["fetched"], blk["no_play"], blk["partial"],
                  blk["error"], blk["bytes"] / 1e6)
    summary["finished_at"] = _now_iso()
    summary["requests"] = n_requests
    tmp = out_dir / "summary.json.tmp"
    tmp.write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(out_dir / "summary.json")
    return summary


def _parse_seasons(s: str) -> list:
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    bad = [x for x in out if x not in HIST_SEASONS]
    if bad:
        raise SystemExit(f"history seasons are {HIST_SEASONS}; refusing {bad} "
                         f"(2018 on lives in .cache/win_prob through mlb_leverage)")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seasons", default="2011-2017,2020")
    ap.add_argument("--limit", type=int, default=None, help="at most N requests this run")
    a = ap.parse_args(argv)
    out_dir = check_out_dir(HIST_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(out_dir / "fetch.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    t0 = time.time()
    summ = run(_parse_seasons(a.seasons), out_dir=out_dir, limit=a.limit)
    tot = sum(b["fetched"] for b in summ["seasons"].values())
    mb = sum(b["bytes"] for b in summ["seasons"].values()) / 1e6
    print(f"done: {tot} payloads, {mb:.1f} MB, {summ['requests']} requests in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
