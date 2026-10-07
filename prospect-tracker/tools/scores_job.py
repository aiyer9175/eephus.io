"""MLB Scores: the intraday job, the only writer of every scores file.

SCORES_2_JOB_AND_DEPLOY (plan SCORES_PLAN.md sections 2, 5, 8, 9 and 17;
pipeline_ops.md sections 1 and 3). The pure builders and the validator live in
`scores_core.py`; this file decides, fetches, writes and keeps its own
telemetry. Owner answers: SC-TERMS (a) the job as planned, SC-JOB (a) box and
here for checks, SC-LIVE (a) the job's own directory behind nginx, SC-HISTORY
(a) back to 2026-03-25, SC-KEEP (a) dates every season, games two.

THE SHAPE IS THE LINEUP JOB'S. Cron it every two minutes under TZ=UTC and let it
decide. `decide()` is pure and does all of its clock reasoning on UTC instants
read off this job's own `.cache/scores/slate.json` and `state.json`, never a
tracked file, so it is correct under any box timezone.

WHERE IT WRITES. While `scores_core.SCORES_LIVE` is False (the module flag,
default False; only SCORES_5a_LIVE_FLIP sets it) every output goes under
`.cache/scores/preview/` whatever the environment says. Once it is True the
output directory is `$EEPHUS_SCORES_OUT` (the box sets `/opt/eephus/scores`),
else `.cache/scores/out/`. An output directory or store that resolves inside
the app tree's `data/` (or the webroot) is refused with exit 2 (`bad_out`).
The job writes nothing else: no tracked file, nothing under `data/`, no shared
cache, not the webroot, not `prospects.db`, and it never opens the nightly's
lock. `OUT/standings/` is reserved for STANDINGS_2 and this job writes nothing
there.

THE NETWORK. One host, `statsapi.mlb.com`, through a job-local urllib session
with no retries (never `feed_cache.SESSION`, whose Retry sleeps Retry-After
inside a call). Every request gets a deadline of min(15 s, the invocation's
remaining budget); 0.5 s between requests; at most 60 requests and 90 s per
invocation, no new request after 75 s; unfinished work rolls over, the
oldest-updated game first. A 429 or 503 (and any Retry-After) sets the job's
`backoff_until` (120 s x 2^(n-1), capped at 1,800 s) and ends the invocation;
another per-game failure sets that game's `stale_since` and its own backoff
and is counted apart (`game_fetch_failed`). The job never calls the house
getters `feed_cache.get_game_feed` or `mlb_leverage.get_win_probability` and
never writes `.cache/game_feeds`, `.cache/win_prob` or `.cache/win_prob_post`.

THE PREGAME BLOCK (SCORES_6). A Preview game's date-file card carries `pre`:
values copied, never computed, from the served Sports Betting board through
scores_core's key-path allowlist (its preview slice once the served Diamond
gate reads on) and from the served SEM+, management, fantasy, park and eFV
files. The card is rebuilt from the schedule without it once the game leaves
Preview, and the validator refuses it on any other state.

THE EPOCH. While `../_pre_epoch_fwar_2026-10/` exists and part 9 of
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` has no step Z entry, the job
exits 0 with action `epoch_hold` before any request or write except its
heartbeat and run-log line. When unsure whether a line is the step Z entry, it
holds.

    python tools/scores_job.py                    # the cron entry point
    python tools/scores_job.py --why              # the gate's opinion; no call, no write
    python tools/scores_job.py --dry-run          # what this tick would fetch; no call, no write
    python tools/scores_job.py --selfcheck        # has the scheduler reached the job here
    python tools/scores_job.py --date 2026-10-03  # rebuild one official date now
    python tools/scores_job.py --backfill 2026-03-25:2026-09-28
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import logging.handlers
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scores_core as sc  # noqa: E402  (standard library only; no pandas, numpy or requests)

log = logging.getLogger("scores_job")

# --------------------------------------------------------------------------- #
# Owner answers (DECISIONS_FOR_OWNER.md, MLB Scores batches 1 and 2)
# --------------------------------------------------------------------------- #
SC_TERMS = "a"        # the scores job as planned; (c) would slow every cadence below
SC_HISTORY = "a"      # backfill 2026 from its first date
SC_KEEP = "a"         # date files every season; game and work files two seasons

#: The earliest official date the week cycle rebuilds or --backfill accepts
#: (SC-HISTORY (a): the 2026 season's first date).
HISTORY_FLOOR = "2026-03-25"

# --------------------------------------------------------------------------- #
# Where things live
# --------------------------------------------------------------------------- #
DATA_DIR = ROOT / "data"
DEFAULT_STORE = ROOT / ".cache" / "scores"
#: Read-only, and only by --backfill (plan 2.1): cached finals the house walks
#: already hold. Never written here, never opened through the house getters.
HOUSE_WP_CACHE = ROOT / ".cache" / "win_prob"
HOUSE_FEED_CACHE = ROOT / ".cache" / "game_feeds"
#: The fWAR label epoch's step A snapshot and the gate whose part 9 records step Z.
EPOCH_SNAPSHOT = ROOT.parent / "_pre_epoch_fwar_2026-10"
EPOCH_GATE_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
#: Subdirectories of OUT this job never writes (STANDINGS_2 owns standings/).
RESERVED_OUT_DIRS = ("standings",)
#: The kill switch file for embedded video (plan 6.7, 17.9), read from OUT.
EMBED_OFF_NAME = "EMBED_OFF"

# --------------------------------------------------------------------------- #
# Cadence (plan 2.1), all compared on cron ticks
# --------------------------------------------------------------------------- #
TICK_S = 120
JITTER_MAX_S = 20
LIVE_GATE_S = 280 if SC_TERMS == "c" else 90
IDLE_INTERVAL_S = 3600 if SC_TERMS == "c" else 1800
OFFSEASON_INTERVAL_S = 21600
WEEK_HOUR_UTC = 10
LIVE_PRE_S = 20 * 60          # Preview within 20 minutes of first pitch
LIVE_POST_S = 20 * 60         # Final within the last 20 minutes
STALE_PREVIEW_S = 6 * 3600    # a Preview game this far past its start is bad data, not live
OFFSEASON_HORIZON_S = 7 * 86400
GAME_WP_MIN_INTERVAL_S = 90
BOX_INTERVAL_S = 600
FINAL_REFRESH_MIN = (60, 180)
NEXT_BY_GRACE_S = 360
DOWN_AFTER_S = 1800
POLL_LIVE_S = 45
POLL_IDLE_S = 300
REBUILD_MAX_DATES = 5
REBUILD_MAX_TRIES = 3         # a past date MLB still lists as unplayed is rebuilt at most this often
GIVE_UP_FAILS = 6             # a game whose reads fail this often leaves the due queue
FINAL_REFRESH_WITHIN_S = 86400
#: Content (SCORES_4a, plan 6.6): while live, a read when a top-five play has
#: no result clip, its plate appearance ended at least 90 s ago and the last
#: read is at least 240 s old; otherwise every 600 s. At Final, +60 and +180
#: minutes and in the finalize cycle with the other final reads.
CONTENT_AFTER_PA_S = 90
CONTENT_LIVE_MIN_S = 240
CONTENT_LIVE_EVERY_S = 600
RUNLOG_KEEP_DAYS = 14

# --------------------------------------------------------------------------- #
# The limiter (plan 2.1)
# --------------------------------------------------------------------------- #
MIN_SPACING_S = 0.5
MAX_REQUESTS_PER_RUN = 60
RUN_DEADLINE_S = 90
LAST_START_S = 75
REQUEST_TIMEOUT_S = 15
BACKOFF_BASE_S = 120
BACKOFF_CAP_S = 1800
RETRY_AFTER_CAP_S = 21600
BACKFILL_RELEASE_EVERY = 50
BACKFILL_REFUSE_UTC_HOURS = (6, 11)    # 06:00 to 11:00 UTC: the nightly's window
BACKFILL_CHUNK_DAYS = 7
#: A slate older than this says nothing about what is live now (the job has
#: not run since), so --backfill does not refuse on it.
BACKFILL_SLATE_TRUST_S = 3 * 3600

# --------------------------------------------------------------------------- #
# StatsAPI (one host; every shape verified with one live GET on 2026-10-03)
# --------------------------------------------------------------------------- #
HOST = "statsapi.mlb.com"
USER_AGENT = "eephus.io scores job (+https://eephus.io/scores/)"
GAME_TYPES = "R,F,D,L,W,A"
SCHEDULE_HYDRATE = "team,linescore,probablePitcher,decisions,seriesStatus,lineups,flags,weather,broadcasts(all)"
WP_FIELDS = ("homeTeamWinProbability,homeTeamWinProbabilityAdded,leverageIndex,about,atBatIndex,inning,"
             "halfInning,isComplete,endTime,result,description,event,eventType,awayScore,homeScore,matchup,"
             "batter,pitcher,id,fullName,count,outs,playEvents,playId,isPitch,"
             "runners,movement,start,end,details,runner,rbi,isOut,postOnFirst,postOnSecond,postOnThird")
PEOPLE_HYDRATE = "stats(group=[pitching],type=[season])"
#: The October bracket (SCORES_4b, plan 1.6): one call per idle cycle from the
#: first postseason date to the last, inside the limiter; series state and
#: results only (scores_core.build_bracket).
BRACKET_PATH = "/api/v1/schedule/postseason/series"
BRACKET_TYPES = ("F", "D", "L", "W")
#: The served registry rows index.json's registry block carries, and the source
#: each row's sentence names (plan 4, the labelling rule).
REGISTRY_IDS = {"scores_mlb_wp": "MLB", "scores_stars_rule": "Eephus rule",
                "scores_biggest_plays_rule": "Eephus rule",
                # SCORES_6: the pregame block's sources (plan 4); the model row's
                # sentence also carries the board's own state ("unvalidated")
                "betting_game_prob": "Eephus model", "sem_plus": "MLB Stats SEM+",
                "efv_v2": "PROSPX eFV", "mgmt_board_export": "In-Game Management"}

#: SCORES_6 served reads (plan 9): the board through scores_core's key-path
#: allowlist (the preview slice once the served Diamond gate reads on), and
#: the files whose values the pregame block copies. data/xfv.json (9.4 MB) and
#: the link table are parsed only when their mtimes move; the joined map is
#: kept in state.json.
BOARD_NAMES = {"full": "betting.json", "preview": "betting_preview.json"}
PRE_SOURCES = {"sem": "starter_leaderboards.json", "hook": "management_board.json", "fantasy": "fantasy.json",
               "park": "fa_meta.json", "xfv": "xfv.json", "links": "player_links.json"}

#: Actions that mean the job could not do its job; exit 2.
LOUD_ACTIONS = ("fetch_failed", "refused", "publish_failed", "bad_out")

# Calls made by this process, by whoever made them (the lineup job's idiom).
CALLS = {"n": 0, "urls": []}


def reset_calls() -> None:
    CALLS["n"] = 0
    CALLS["urls"] = []


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def store_dir() -> Path:
    env = os.environ.get("EEPHUS_SCORES_STORE")
    return Path(env) if env else DEFAULT_STORE


def out_dir() -> Path:
    """OUT follows the module flag: the preview directory while it is False,
    whatever the environment says."""
    if not sc.SCORES_LIVE:
        return store_dir() / "preview"
    env = os.environ.get("EEPHUS_SCORES_OUT")
    return Path(env) if env else store_dir() / "out"


def served_data_dir() -> Path:
    """The SERVED copy of data/ (the box's webroot when EEPHUS_WEBROOT is set),
    because the app tree can hold files a red nightly gate never published."""
    web = os.environ.get("EEPHUS_WEBROOT")
    return Path(web) / "data" if web else DATA_DIR


def resolve_paths() -> dict:
    """Every path this job may write, resolved. A test asserts that under
    pytest each one sits inside the session temp directory."""
    st = store_dir()
    out = out_dir()
    return {"store": st, "out": out, "slate": st / "slate.json", "state": st / "state.json",
            "sig": st / "sig.json", "heartbeat": st / "heartbeat.json", "lock": st / "job.lock",
            "work": st / "work", "runlog_dir": st}


def _inside(child: Path, parent: Path) -> bool:
    try:
        c = os.path.normcase(str(Path(child).resolve()))
        p = os.path.normcase(str(Path(parent).resolve()))
    except OSError:
        return False
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:
        return False


def bad_out(paths: dict) -> str | None:
    """Why the output or the store may not be used, or None. The job never
    writes under the app tree's data/ (the nightly's checkout and step A's
    stability read watch it) or inside the webroot (the nightly's rsync
    --delete owns it)."""
    for key in ("out", "store"):
        if _inside(paths[key], DATA_DIR):
            return f"{key} {paths[key]} resolves inside the app tree's data/"
    web = os.environ.get("EEPHUS_WEBROOT")
    if web and _inside(paths["out"], Path(web)):
        return f"out {paths['out']} resolves inside the webroot {web}"
    return None


# --------------------------------------------------------------------------- #
# Instants
# --------------------------------------------------------------------------- #
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_stamp(s) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt) -> str:
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt, timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def tick_of(start_epoch: float) -> int:
    """The cron tick a cycle is stamped at: floor(start / 120) * 120, taken
    from the process start BEFORE the jitter sleep."""
    return int(start_epoch // TICK_S) * TICK_S


def ceil_tick(t: float) -> int:
    return int(-(-int(t) // TICK_S)) * TICK_S


def utc_date(dt: datetime) -> date:
    return dt.astimezone(timezone.utc).date()


# --------------------------------------------------------------------------- #
# The epoch hold
# --------------------------------------------------------------------------- #
_STEP_Z_HEDGE = re.compile(r"\b(before|after|until|till|about|earliest|proposed|expected|planned|once|when|by|to|at|"
                           r"from|reach|reaches|reached|awaiting|pending)\s+step Z\b", re.IGNORECASE)


def step_z_entry(text: str | None = None) -> str | None:
    """The date of part 9's step Z entry, or None. A line counts only when it
    carries a date and names step Z as what happened, not as a time reference
    ("after step Z", "before step Z" and the like never count): when unsure,
    hold."""
    if text is None:
        try:
            text = EPOCH_GATE_DOC.read_text(encoding="utf-8")
        except OSError:
            return None
    if "## 9. Results" not in text:
        return None
    part9 = text.split("## 9. Results", 1)[1]
    for line in part9.splitlines():
        m = re.search(r"(\d{4}-\d{2}-\d{2})[^\n]*\bstep Z\b", line)
        if m and not _STEP_Z_HEDGE.search(line):
            return m.group(1)
    return None


def epoch_hold() -> tuple[bool, str]:
    if not EPOCH_SNAPSHOT.exists():
        return False, "no step A snapshot"
    z = step_z_entry()
    if z is None:
        return True, (f"{EPOCH_SNAPSHOT.name} exists and part 9 of {EPOCH_GATE_DOC.name} has no step Z "
                      f"entry: the fWAR label epoch is running, so the job holds")
    return False, f"step Z recorded {z}"


# --------------------------------------------------------------------------- #
# The network: one host, one job-local session, a deadline on every request
# --------------------------------------------------------------------------- #
class RateLimited(Exception):
    """A 429 or 503: the job backs off and ends the invocation."""

    def __init__(self, status: int, retry_after: float | None, url: str):
        super().__init__(f"HTTP {status} from {url}")
        self.status, self.retry_after, self.url = status, retry_after, url


class FetchError(Exception):
    def __init__(self, msg: str, status: int | None = None, url: str = ""):
        super().__init__(msg)
        self.status, self.url = status, url


class BudgetExhausted(Exception):
    """No new request may start in this invocation (count or time)."""


def parse_retry_after(value, now: float | None = None) -> float | None:
    if value is None:
        return None
    v = str(value).strip()
    if v.isdigit():
        return float(v)
    try:
        dt = parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, dt.timestamp() - (now if now is not None else time.time()))


def urllib_adapter(url: str, timeout: float) -> tuple[int, dict, bytes]:
    """One GET with no retry. The whole exchange, connect to last byte, is held
    to `timeout` seconds: the socket timeout bounds each read and the loop
    bounds their sum."""
    t_end = time.monotonic() + timeout
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip",
                                               "Accept": "application/json"})
    try:
        fh = urllib.request.urlopen(req, timeout=max(0.5, timeout))
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        return int(e.code), hdrs, b""
    with fh:
        hdrs = {k.lower(): v for k, v in fh.headers.items()}
        chunks = []
        while True:
            if time.monotonic() > t_end:
                raise TimeoutError(f"deadline of {timeout:.1f} s passed reading {url}")
            b = fh.read(65536)
            if not b:
                break
            chunks.append(b)
        body = b"".join(chunks)
        if hdrs.get("content-encoding") == "gzip":
            body = gzip.decompress(body)
        return int(fh.status), hdrs, body


class Limiter:
    """The per-invocation budget: requests, spacing and the wall-clock bound.
    The clock and the sleep are injectable so a test can prove the bounds
    without waiting. Reusable by a second file family (STANDINGS_2)."""

    def __init__(self, *, max_requests: int = MAX_REQUESTS_PER_RUN, run_deadline_s: float = RUN_DEADLINE_S,
                 last_start_s: float = LAST_START_S, spacing_s: float = MIN_SPACING_S,
                 request_timeout_s: float = REQUEST_TIMEOUT_S, clock=time.monotonic, sleep=time.sleep):
        self.max_requests, self.run_deadline_s, self.last_start_s = max_requests, run_deadline_s, last_start_s
        self.spacing_s, self.request_timeout_s = spacing_s, request_timeout_s
        self.clock, self.sleep = clock, sleep
        self.t0 = clock()
        self.n = 0
        self.last_end: float | None = None

    def elapsed(self) -> float:
        return self.clock() - self.t0

    def can_start(self) -> bool:
        return self.n < self.max_requests and self.elapsed() < self.last_start_s

    def acquire(self) -> float:
        """Wait out the spacing and return this request's deadline in seconds;
        raise BudgetExhausted when no new request may start."""
        if not self.can_start():
            raise BudgetExhausted(f"{self.n} requests, {self.elapsed():.1f} s")
        if self.last_end is not None:
            gap = self.spacing_s - (self.clock() - self.last_end)
            if gap > 0:
                self.sleep(gap)
        if not self.can_start():
            raise BudgetExhausted(f"{self.n} requests, {self.elapsed():.1f} s")
        self.n += 1
        return max(0.1, min(self.request_timeout_s, self.run_deadline_s - self.elapsed()))

    def release(self) -> None:
        self.last_end = self.clock()


class Fetcher:
    """GETs against statsapi.mlb.com only, through the limiter."""

    def __init__(self, limiter: Limiter, adapter=None):
        self.limiter = limiter
        self.adapter = adapter or urllib_adapter
        self.statuses: list[int] = []

    def url(self, path: str, params: dict | None = None) -> str:
        q = ("?" + urllib.parse.urlencode(params, safe="(),")) if params else ""
        return f"https://{HOST}{path}{q}"

    def get(self, path: str, params: dict | None = None):
        url = self.url(path, params)
        if urllib.parse.urlsplit(url).hostname != HOST:      # belt and braces: one host only
            raise FetchError(f"refused host in {url}", url=url)
        timeout = self.limiter.acquire()
        CALLS["n"] += 1
        CALLS["urls"].append(url)
        try:
            status, headers, body = self.adapter(url, timeout)
        except (TimeoutError, OSError, ValueError) as e:
            self.statuses.append(0)
            raise FetchError(f"{type(e).__name__}: {e}", url=url) from e
        finally:
            self.limiter.release()
        self.statuses.append(int(status))
        if status in (429, 503):
            raise RateLimited(int(status), parse_retry_after((headers or {}).get("retry-after")), url)
        if status != 200:
            raise FetchError(f"HTTP {status}", status=int(status), url=url)
        try:
            return json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
        except (ValueError, UnicodeDecodeError) as e:
            raise FetchError(f"unparseable body: {e}", status=int(status), url=url) from e

    # the request shapes (each verified with one live GET: the first five on
    # 2026-10-03, the postseason series on 2026-10-07)
    def schedule(self, start: str, end: str, *, hydrate: bool = True):
        params = {"sportId": 1, "startDate": start, "endDate": end, "gameType": GAME_TYPES}
        if hydrate:
            params["hydrate"] = SCHEDULE_HYDRATE
        return self.get("/api/v1/schedule", params)

    def win_probability(self, pk: int):
        return self.get(f"/api/v1/game/{int(pk)}/winProbability", {"fields": WP_FIELDS})

    def boxscore(self, pk: int):
        return self.get(f"/api/v1/game/{int(pk)}/boxscore")

    def feed(self, pk: int):
        return self.get(f"/api/v1.1/game/{int(pk)}/feed/live")

    def people(self, ids):
        return self.get("/api/v1/people", {"personIds": ",".join(str(int(i)) for i in sorted(set(ids))),
                                           "hydrate": PEOPLE_HYDRATE})

    def content(self, pk: int):
        """The game's content (SCORES_4a; plan 6.1). `/content` ignores
        `fields=`, so every call costs the full payload (plan 6.6)."""
        return self.get(f"/api/v1/game/{int(pk)}/content")

    def postseason_series(self, season: int):
        return self.get(BRACKET_PATH, {"sportId": 1, "season": int(season)})


# --------------------------------------------------------------------------- #
# The lock: an OS advisory lock the OS releases when the process exits
# --------------------------------------------------------------------------- #
class JobLock:
    """`fcntl.flock` on POSIX, `msvcrt.locking` on Windows, on
    `.cache/scores/job.lock`. A killed holder leaves nothing that blocks the
    next run, because the lock dies with the process. Never the nightly's
    `/tmp/eephus-nightly.lock`."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def release(self) -> None:
        if self.fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.fh.close()
            self.fh = None


# --------------------------------------------------------------------------- #
# Bytes on disk: same-directory temp file, 0644, os.replace with retries
# --------------------------------------------------------------------------- #
class ReplaceBusy(Exception):
    pass


def _mkdirs(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True, mode=0o755)
    if os.name != "nt":
        try:
            os.chmod(d, 0o755)
        except OSError:
            pass


def write_bytes(path: Path, data: bytes, *, retries: int = 5, retry_sleep: float = 0.05) -> None:
    """Never `feed_cache.atomic_write_json` (its mkstemp file is 0600 and would
    reach nginx unreadable)."""
    path = Path(path)
    _mkdirs(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{random.randrange(1 << 30):x}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o644)
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
    finally:
        os.close(fd)
    for attempt in range(retries + 1):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == retries:
                raise ReplaceBusy(f"replace_busy: {path} (temp file left at {tmp.name})")
            time.sleep(retry_sleep)


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json_plain(path: Path, obj) -> None:
    """The job's own .cache files (state, slate, heartbeat, work)."""
    write_bytes(path, json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class Writer:
    """Validated writes into OUT: the validator of plan 8.5 runs before every
    replace (with its on-disk rules: generated_at never older than the file on
    disk, the shrink guard), a refusal keeps that file's last good copy, and
    every write goes through `write_bytes`. Reusable by a second file family
    through `validate` and `kinds`."""

    def __init__(self, out: Path, *, validate=None):
        self.out = Path(out)
        self.validate = validate or sc.validate_payload
        self.results: dict = {}
        self._cache: dict = {}

    def path(self, rel: str) -> Path:
        rel = rel.replace("\\", "/")
        if rel.split("/")[0] in RESERVED_OUT_DIRS:
            raise ValueError(f"{rel}: OUT/{rel.split('/')[0]}/ is reserved for another job")
        return self.out / rel

    def read(self, rel: str):
        """The file on disk, parsed (memoized for the cycle; a write replaces
        the memo)."""
        if rel not in self._cache:
            self._cache[rel] = read_json(self.path(rel))
        return self._cache[rel]

    def disk_rev(self, rel: str) -> str | None:
        try:
            return sc.rev_of(self.path(rel).read_bytes())
        except OSError:
            return None

    def write(self, rel: str, kind: str, obj, *, extra_refusals=()) -> dict:
        prev = self.read(rel)
        disk_gen = prev.get("generated_at") if isinstance(prev, dict) else None
        res = self.validate(kind, obj, name=rel, disk_generated_at=disk_gen)
        refused = list(res.get("refused") or []) + list(extra_refusals)
        out = {"rel": rel, "kind": kind, "ok": not refused, "refused": refused,
               "logged": list(res.get("logged") or []), "bytes": res.get("bytes"), "written": False,
               "rev": self.disk_rev(rel)}
        if refused:
            self.results[rel] = out
            return out
        data = sc.dumps(obj).encode("utf-8")
        try:
            write_bytes(self.path(rel), data)
        except ReplaceBusy as e:
            out.update(ok=False, refused=[("publish", str(e))], publish_failed=True)
            self.results[rel] = out
            return out
        self._cache[rel] = json.loads(data.decode("utf-8"))
        out.update(written=True, rev=sc.rev_of(data))
        self.results[rel] = out
        return out


# --------------------------------------------------------------------------- #
# Served reads (the box's webroot when EEPHUS_WEBROOT is set), with carry-forward
# --------------------------------------------------------------------------- #
def read_served(name: str):
    doc = read_json(served_data_dir() / name)
    return doc if doc else None


def served_blocks(state: dict, *, current_season: int) -> dict:
    """The registry rows, the MLB win-probability accuracy keys and the league
    constants, read from the SERVED data/ on every acting cycle; the last good
    block from state.json is used when a read fails or parses empty."""
    keep = state.setdefault("served", {})
    reg = read_served("model_registry.json")
    if isinstance(reg, dict) and isinstance(reg.get("models"), list) and reg["models"]:
        rows = []
        by_id = {m.get("model_id"): m for m in reg["models"] if isinstance(m, dict)}
        for mid, label in REGISTRY_IDS.items():
            m = by_id.get(mid)
            if m and m.get("verdict"):
                rows.append({"model_id": mid, "verdict": m["verdict"], "sentence": f"{label}, {m['verdict']}"})
        keep["registry"] = rows
    we = read_served("win_expectancy.json")
    cal = (we or {}).get("calibration") if isinstance(we, dict) else None
    if isinstance(cal, dict) and cal.get("feed_brier") is not None:
        keep["accuracy"] = {"feed_brier": cal.get("feed_brier"), "base_rate_brier": cal.get("brier_base_rate_only"),
                            "n_plays": we.get("n_plays_fit"), "seasons": list(we.get("seasons") or []),
                            "artifact_generated_at": we.get("generated_at")}
    lc = read_served("league_constants.json")
    seasons = (lc or {}).get("seasons") if isinstance(lc, dict) else None
    if isinstance(seasons, dict) and seasons:
        keep["constants"] = {str(k): {"lg_ra9": v.get("lg_ra9"), "rpw": v.get("rpw")}
                             for k, v in seasons.items() if isinstance(v, dict) and v.get("lg_ra9") and v.get("rpw")}
    # SCORES_6: the board is read fresh on every acting cycle and never carried
    # forward (a failed read shows no model number rather than an old one)
    board, kind = served_board()
    registry = [dict(r) for r in keep.get("registry") or []]
    state_word = ((board or {}).get("file") or {}).get("status.model")
    for r in registry:
        if r["model_id"] == "betting_game_prob" and isinstance(state_word, str) and state_word:
            r["sentence"] = f"{REGISTRY_IDS['betting_game_prob']}, {state_word}, {r['verdict']}"
    return {"registry": registry, "board": board, "board_kind": kind,
            "accuracy": keep.get("accuracy") or {"feed_brier": None, "base_rate_brier": None, "n_plays": None,
                                                 "seasons": [], "artifact_generated_at": None},
            "constants": keep.get("constants") or {}}


def served_board() -> tuple[dict | None, str]:
    """The served board read through scores_core's allowlist, and which file:
    the full board while the served assets/diamond-config.js reads gating
    false, the preview slice (the gate's seam) once it reads true."""
    try:
        cfg = served_diamond_config().read_text(encoding="utf-8")
    except OSError:
        cfg = ""
    kind = "preview" if sc.diamond_gating_on(cfg) else "full"
    return sc.board_extract(read_served(BOARD_NAMES[kind])), kind


def _mtimes(names) -> list | None:
    try:
        return [(served_data_dir() / n).stat().st_mtime for n in names]
    except OSError:
        return None


def efv_map_cached(state: dict) -> dict:
    """{mlbam: xfv_grade} for eFV v2 prospects, re-read from the served
    data/xfv.json and the link table only when either file's mtime moves;
    otherwise the map kept in state.json."""
    keep = state.get("xfv") or {}
    mt = _mtimes((PRE_SOURCES["xfv"], PRE_SOURCES["links"]))
    if mt is None or keep.get("mtimes") == mt:
        return keep.get("map") or {}
    xfv, links = read_served(PRE_SOURCES["xfv"]), read_served(PRE_SOURCES["links"])
    if not isinstance(xfv, dict) or not isinstance(links, dict):
        return keep.get("map") or {}
    m = sc.efv_map(xfv, links)
    state["xfv"] = {"mtimes": mt, "map": m}
    return m


def pregame_context(state: dict, served: dict) -> dict:
    """The served reads a Preview card's `pre` block copies from (plan 9)."""
    two, pks = sc.fantasy_maps(read_served(PRE_SOURCES["fantasy"]))
    return {"board": served.get("board"), "board_kind": served.get("board_kind") or "full",
            "sem": sc.sem_map(read_served(PRE_SOURCES["sem"])),
            "hook": sc.hook_map(read_served(PRE_SOURCES["hook"])),
            "two_start": two, "dfs_pks": pks,
            "park": sc.park_map(read_served(PRE_SOURCES["park"])),
            "efv": efv_map_cached(state)}


def lg_for(constants: dict, season: int) -> dict | None:
    """The served league constants of the game's season, else the nearest
    earlier season held, else the nearest later one; None when none was ever
    read (no constant is typed here, so no star is built without one)."""
    if str(season) in constants:
        return constants[str(season)]
    keys = sorted(int(k) for k in constants if str(k).isdigit())
    earlier = [k for k in keys if k < season]
    pick = earlier[-1] if earlier else (keys[0] if keys else None)
    return constants[str(pick)] if pick is not None else None


def served_diamond_config() -> Path:
    """The SERVED assets/diamond-config.js ($EEPHUS_WEBROOT/assets/ when set)."""
    web = os.environ.get("EEPHUS_WEBROOT")
    return (Path(web) if web else ROOT) / "assets" / "diamond-config.js"


def embed_status(out: Path) -> tuple[bool, str]:
    """The video embed switch (plan 6.7) and why: the module constant
    SCORES_EMBED_VIDEO is only the default; every run also reads the override
    EEPHUS_SCORES_EMBED=0 from the environment (the crontab line) and the flag
    file EMBED_OFF in OUT or in the store (/opt/eephus/scores/EMBED_OFF on the
    box, .cache/scores/EMBED_OFF here). The SC-PAID fail-safe: embedding is off
    whenever the served assets/diamond-config.js reads `gating: true` and
    scores_core.SCORES_EMBED_RECONFIRMED holds no ISO date."""
    if not sc.SCORES_EMBED_VIDEO:
        return False, "SCORES_EMBED_VIDEO is False"
    if os.environ.get("EEPHUS_SCORES_EMBED", "").strip() == "0":
        return False, "EEPHUS_SCORES_EMBED=0"
    for d in (Path(out), store_dir()):
        if (d / EMBED_OFF_NAME).exists():
            return False, f"{EMBED_OFF_NAME} in {d}"
    try:
        cfg = served_diamond_config().read_text(encoding="utf-8")
    except OSError:
        cfg = ""
    if sc.diamond_gating_on(cfg) and not sc.embed_reconfirmed():
        return False, "the Diamond gate reads on and S8-1 is not re-confirmed (SC-PAID fail-safe)"
    return True, "on"


def embed_effective(out: Path) -> bool:
    return embed_status(out)[0]


# --------------------------------------------------------------------------- #
# The slate this job owns
# --------------------------------------------------------------------------- #
def schedule_games(payload) -> list[dict]:
    out = []
    for d in (payload or {}).get("dates", []) or []:
        for g in d.get("games", []) or []:
            if g.get("gamePk"):
                if not g.get("officialDate"):
                    g = dict(g, officialDate=d.get("date"))
                out.append(g)
    return out


def state_hash(g: dict) -> str:
    """inning, half, outs, balls, strikes, both scores, occupied bases, status code."""
    ls = g.get("linescore") or {}
    off = ls.get("offense") or {}
    teams = g.get("teams") or {}
    parts = [ls.get("currentInning"), ls.get("inningHalf"), ls.get("outs"), ls.get("balls"), ls.get("strikes"),
             ((ls.get("teams") or {}).get("away") or {}).get("runs", (teams.get("away") or {}).get("score")),
             ((ls.get("teams") or {}).get("home") or {}).get("runs", (teams.get("home") or {}).get("score")),
             bool(off.get("first")), bool(off.get("second")), bool(off.get("third")),
             (g.get("status") or {}).get("statusCode")]
    return sc.rev_of(json.dumps(parts, default=str))


def slate_row(g: dict, prev: dict | None, now: datetime) -> dict:
    state, _reason = sc.game_state(g.get("status"))
    teams = g.get("teams") or {}
    probables = [int(((teams.get(s) or {}).get("probablePitcher") or {}).get("id"))
                 for s in ("away", "home") if ((teams.get(s) or {}).get("probablePitcher") or {}).get("id")]
    final_seen = (prev or {}).get("final_seen_at")
    if state == "final" and not final_seen:
        final_seen = iso(now)
        start = parse_stamp(g.get("gameDate"))
        if prev is None and start is not None:
            # first seen already final (a first run, or a game the job never saw
            # live): stamp it no later than three hours after first pitch, so an
            # old final never opens a live window or a +60 refresh
            final_seen = iso(min(now, start + timedelta(hours=3)))
    if state != "final":
        final_seen = None
    return {"pk": int(g["gamePk"]), "date": g.get("officialDate"), "type": g.get("gameType"),
            "season": sc._int(g.get("season"), 0) or sc._int(str(g.get("officialDate") or "")[:4], 0),
            "start": g.get("gameDate"), "tbd": bool((g.get("status") or {}).get("startTimeTBD")),
            "state": state, "hash": state_hash(g), "final_seen_at": final_seen, "probables": probables}


def merge_slate(slate: dict | None, games: list[dict], span: tuple[str, str], now: datetime) -> dict:
    """Rows from this fetch replace the rows of the dates it covers; rows of
    other dates inside D-1 to D+7 are kept; everything else drops."""
    old = {r["pk"]: r for r in ((slate or {}).get("games") or [])}
    rows = {}
    for g in games:
        r = slate_row(g, old.get(int(g["gamePk"])), now)
        rows[r["pk"]] = r
    d = utc_date(now)
    lo, hi = (d - timedelta(days=1)).isoformat(), (d + timedelta(days=7)).isoformat()
    for pk, r in old.items():
        if pk in rows:
            continue
        rd = r.get("date") or ""
        if span[0] <= rd <= span[1]:
            continue                                    # this fetch covered the date and the game is gone
        if lo <= rd <= hi:
            rows[pk] = r
    return {"fetched_at": iso(now), "span": list(span), "games": sorted(rows.values(), key=lambda r: (r["date"] or "", r["start"] or "", r["pk"]))}


# --------------------------------------------------------------------------- #
# The decision. PURE: reads the slate and the state passed in, writes nothing.
# --------------------------------------------------------------------------- #
def _start_epoch(row) -> float | None:
    dt = parse_stamp(row.get("start"))
    return dt.timestamp() if dt else None


def live_games(rows: list[dict], now: datetime) -> list[dict]:
    """Games that put the job on live cycles: Live (Warmup, In Progress,
    delays, challenges), Preview within 20 minutes of first pitch (or past it
    and not yet started), or Final within the last 20 minutes."""
    t = now.timestamp()
    out = []
    for r in rows or []:
        st = r.get("state")
        if st in ("live", "delayed"):
            out.append(r)
        elif st in ("scheduled", "pregame"):
            s = _start_epoch(r)
            if s is not None and not r.get("tbd") and -STALE_PREVIEW_S <= s - t <= LIVE_PRE_S:
                out.append(r)
        elif st == "final":
            f = parse_stamp(r.get("final_seen_at"))
            if f is not None and 0 <= t - f.timestamp() <= LIVE_POST_S:
                out.append(r)
    return out


def is_offseason(rows: list[dict], now: datetime) -> bool:
    t = now.timestamp()
    for r in rows or []:
        if r.get("state") in ("live", "delayed"):
            return False
        s = _start_epoch(r)
        if s is not None and t - 86400 <= s <= t + OFFSEASON_HORIZON_S:
            return False
    return True


def final_refresh_due(state: dict, now: datetime) -> list[tuple[int, int]]:
    """(pk, minutes) for every Final +60 or +180 minute refresh now due."""
    out = []
    t = now.timestamp()
    for pk, g in (state.get("games") or {}).items():
        f = parse_stamp(g.get("final_seen_at"))
        if f is None or g.get("frozen") or not g.get("final_built") or t - f.timestamp() > FINAL_REFRESH_WITHIN_S:
            continue
        if float(g.get("backoff_until") or 0) > t:
            continue
        done = set(g.get("refreshed") or [])
        for m in FINAL_REFRESH_MIN:
            if m not in done and t >= f.timestamp() + m * 60:
                out.append((int(pk), m))
                break
    return out


def due_reasons(state: dict, now: datetime, embed: bool | None) -> list[str]:
    st = state or {}
    pend = st.get("pending") or {}
    t = now.timestamp()
    games = st.get("games") or {}

    def ready(pk) -> bool:
        return float((games.get(str(pk)) or {}).get("backoff_until") or 0) <= t

    out = []
    roll = [pk for pk in pend.get("rollover") or [] if ready(pk)]
    if roll:
        out.append(f"rollover:{len(roll)}")
    fin = [pk for pk in pend.get("finalize") or [] if ready(pk)]
    if fin:
        out.append(f"finalize:{len(fin)}")
    if pend.get("rebuild"):
        out.append(f"rebuild:{len(pend['rebuild'])}")
    ref = final_refresh_due(st, now)
    if ref:
        out.append(f"final_refresh:{len(ref)}")
    if embed is not None and st.get("embed") is not None and bool(embed) != bool(st.get("embed")):
        out.append("embed_switch")
    return out


def next_week_tick(now: datetime, state: dict) -> int:
    d = utc_date(now)
    today10 = datetime(d.year, d.month, d.day, WEEK_HOUR_UTC, tzinfo=timezone.utc)
    if now < today10 and (state or {}).get("week_date") != d.isoformat():
        return ceil_tick(today10.timestamp())
    return ceil_tick((today10 + timedelta(days=1)).timestamp())


def next_by(tick: int, rows: list[dict], now: datetime, state: dict) -> str:
    """The tick of the next acting cycle the job expects, plus 360 s of grace
    (plan 2.4): the next live tick while a game is live or within 20 minutes of
    first pitch; else the last idle tick plus 1,800 s capped at the next switch
    to live cycles; the last offseason tick plus 21,600 s in the offseason; and
    the next 10:00 UTC week tick when that comes first."""
    if live_games(rows, now):
        nxt = ceil_tick(tick + LIVE_GATE_S)
    elif is_offseason(rows, now):
        nxt = tick + OFFSEASON_INTERVAL_S
    else:
        nxt = tick + IDLE_INTERVAL_S
        t = now.timestamp()
        switches = [s - LIVE_PRE_S for s in (_start_epoch(r) for r in rows or []
                                             if r.get("state") in ("scheduled", "pregame") and not r.get("tbd"))
                    if s is not None and s - LIVE_PRE_S > t]
        if switches:
            nxt = min(nxt, ceil_tick(min(switches)))
    nxt = min(nxt, next_week_tick(now, state))
    return iso(nxt + NEXT_BY_GRACE_S)


def decide(now: datetime | None = None, slate: dict | None = None, state: dict | None = None, *,
           tick: int | None = None, embed: bool | None = None) -> dict:
    """Should this invocation act, and as which cycle? Returns the decision
    and its reasoning, so --why and the real run cannot disagree."""
    now = now or _utcnow()
    tick = tick if tick is not None else tick_of(now.timestamp())
    st = state or {}
    rows = (slate or {}).get("games") or []
    out = {"now": iso(now), "tick": tick, "tick_at": iso(tick), "acts": False, "action": "none", "cycle": None,
           "reason": "", "due": [], "live_games": 0}
    bu = st.get("backoff_until")
    if bu and float(bu) > now.timestamp():
        out.update(action="backoff", reason=f"job-level backoff until {iso(float(bu))} (n={st.get('backoff_n')})")
        return out
    live = live_games(rows, now)
    out["live_games"] = len(live)
    week_due = now.hour >= WEEK_HOUR_UTC and st.get("week_date") != utc_date(now).isoformat()
    last_any, last_live = st.get("last_cycle_tick"), st.get("last_live_tick")
    due = due_reasons(st, now, embed)
    out["due"] = due
    offseason = bool(slate) and is_offseason(rows, now)
    if not slate:
        cyc = "week" if week_due else "idle"
        out.update(acts=True, action=cyc, cycle=cyc,
                   reason="no_local_slate: this job has no slate here yet, so it establishes one")
    elif week_due:
        out.update(acts=True, action="week", cycle="week",
                   reason=f"the first invocation at or after {WEEK_HOUR_UTC}:00 UTC on {utc_date(now).isoformat()}")
    elif live and (last_live is None or tick - int(last_live) >= LIVE_GATE_S):
        out.update(acts=True, action="live", cycle="live",
                   reason=f"{len(live)} game(s) live or within 20 minutes of first pitch or of the final")
    elif due:
        out.update(acts=True, action="due", cycle="due", reason="due work: " + ", ".join(due))
    elif live:
        out.update(reason=f"live, but the last live cycle was {tick - int(last_live)} s of ticks ago "
                          f"(gate {LIVE_GATE_S} s)")
    elif offseason:
        if last_any is None or tick - int(last_any) >= OFFSEASON_INTERVAL_S:
            out.update(acts=True, action="offseason", cycle="offseason", reason="no game within 7 days")
        else:
            out.update(reason=f"offseason; the last cycle was {tick - int(last_any)} s of ticks ago")
    elif last_any is None or tick - int(last_any) >= IDLE_INTERVAL_S:
        out.update(acts=True, action="idle", cycle="idle", reason="no live game; the idle refresh is due")
    else:
        out.update(reason=f"no live game; the last cycle was {tick - int(last_any)} s of ticks ago "
                          f"(idle every {IDLE_INTERVAL_S} s)")
    out["next_by"] = next_by(tick, rows, now, st)
    return out


# --------------------------------------------------------------------------- #
# Per-game work
# --------------------------------------------------------------------------- #
def _gstate(state: dict, pk: int) -> dict:
    return state.setdefault("games", {}).setdefault(str(int(pk)), {})


def work_path(paths: dict, pk: int) -> Path:
    return paths["work"] / f"{int(pk)}.json"


def read_work(paths: dict, pk: int) -> dict:
    return read_json(work_path(paths, pk)) or {"pk": int(pk)}


def trim_feed(feed: dict | None) -> dict | None:
    """What the builders read from the feed: gameData and the officials."""
    if not isinstance(feed, dict):
        return None
    return {"gameData": feed.get("gameData") or {},
            "liveData": {"boxscore": {"officials": (((feed.get("liveData") or {}).get("boxscore") or {})
                                                    .get("officials")) or []}}}


def plan_tasks(games: list[dict], state: dict, now: datetime, cycle: str, tick: int) -> list[dict]:
    """The per-game calls this cycle wants, live work first, each group oldest
    updated first so a starved game goes first on the next tick."""
    t = now.timestamp()
    live_wp, live_box, live_content, finals, refresh = [], [], [], [], []
    by_pk = {int(g["gamePk"]): g for g in games}
    for pk, g in by_pk.items():
        gs = (state.get("games") or {}).get(str(pk)) or {}
        if gs.get("frozen"):
            continue
        if float(gs.get("backoff_until") or 0) > t:
            continue
        st, _ = sc.game_state(g.get("status"))
        upd = float(gs.get("updated_epoch") or 0)
        if st in ("live", "delayed") and (g.get("linescore") or {}).get("currentInning"):
            h = state_hash(g)
            if (h != gs.get("wp_hash") or not gs.get("wp_epoch")) and t - float(gs.get("wp_epoch") or 0) >= GAME_WP_MIN_INTERVAL_S:
                live_wp.append({"pk": pk, "calls": ["wp"], "why": "live", "order": upd})
            if t - float(gs.get("box_epoch") or 0) >= BOX_INTERVAL_S:
                live_box.append({"pk": pk, "calls": ["box"], "why": "live_box", "order": upd})
            if content_due(gs, t):
                live_content.append({"pk": pk, "calls": ["content"], "why": "live_content", "order": upd})
        elif st == "final" and not gs.get("final_built"):
            finals.append({"pk": pk, "calls": ["wp", "box", "feed", "content"], "why": "final", "order": upd})
    for pk, m in final_refresh_due(state, now):
        if pk in by_pk:
            refresh.append({"pk": pk, "calls": ["wp", "box", "content"], "why": f"final_refresh_{m}", "minutes": m,
                            "order": float(((state.get("games") or {}).get(str(pk)) or {}).get("updated_epoch") or 0)})
    pend = state.get("pending") or {}
    roll = {int(x) for x in pend.get("rollover") or []}
    fin = [int(x) for x in pend.get("finalize") or [] if int(x) in by_pk]
    groups = []
    for grp in (live_wp, live_box, live_content, finals, refresh):
        grp.sort(key=lambda x: (0 if x["pk"] in roll else 1, x["order"], x["pk"]))
        groups.extend(grp)
    planned = {x["pk"] for x in finals}
    for pk in sorted(fin, key=lambda p: float(((state.get("games") or {}).get(str(p)) or {}).get("updated_epoch") or 0)):
        gs = (state.get("games") or {}).get(str(pk)) or {}
        if pk in planned or gs.get("frozen") or float(gs.get("backoff_until") or 0) > t:
            continue
        groups.append({"pk": pk, "calls": ["wp", "box", "feed", "content"], "why": "finalize", "order": 0})
    return groups


def content_due(gs: dict, t: float) -> bool:
    """Plan 6.6 for a live game: a read when a top-five play has no result
    clip, its plate appearance ended at least 90 s ago (`content_due_at`, set
    when the game file is built) and the last read is at least 240 s old;
    otherwise every 600 s."""
    last = float(gs.get("content_epoch") or 0)
    due_at = gs.get("content_due_at")
    if due_at is not None and t >= float(due_at) and t - last >= CONTENT_LIVE_MIN_S:
        return True
    return t - last >= CONTENT_LIVE_EVERY_S


def mark_backoff(state: dict, now: datetime, retry_after: float | None) -> None:
    n = int(state.get("backoff_n") or 0) + 1
    wait = min(BACKOFF_BASE_S * 2 ** (n - 1), BACKOFF_CAP_S)
    if retry_after is not None:
        wait = max(wait, min(float(retry_after), RETRY_AFTER_CAP_S))
    state["backoff_n"] = n
    state["backoff_until"] = now.timestamp() + wait


def mark_game_failure(state: dict, pk: int, now: datetime, err: str) -> None:
    gs = _gstate(state, pk)
    n = int(gs.get("fail_n") or 0) + 1
    gs["fail_n"] = n
    gs["backoff_until"] = now.timestamp() + min(BACKOFF_BASE_S * 2 ** (n - 1), BACKOFF_CAP_S)
    gs["stale_since"] = gs.get("stale_since") or iso(now)
    gs["last_error"] = err[:200]


def run_tasks(tasks: list[dict], fetcher: Fetcher, state: dict, paths: dict, now_fn, counts: dict) -> dict:
    """Execute the planned calls inside the limiter. Returns
    {done: {pk: why}, rolled: [pk], rate_limited: RateLimited|None}."""
    done: dict = {}
    rolled: list = []
    failed: set = set()
    rl = None
    for i, task in enumerate(tasks):
        pk = task["pk"]
        if rl is not None or not fetcher.limiter.can_start():
            rolled.extend(t["pk"] for t in tasks[i:] if t["pk"] not in rolled and t["pk"] not in failed)
            break
        if pk in failed:
            continue                        # one failure per game per invocation; its backoff covers the rest
        work = read_work(paths, pk)
        ok = True
        for call in task["calls"]:
            try:
                if call == "wp":
                    work["wp"] = fetcher.win_probability(pk)
                    work["wp_at"] = iso(now_fn())
                elif call == "box":
                    work["box"] = fetcher.boxscore(pk)
                    work["box_at"] = iso(now_fn())
                elif call == "feed":
                    work["feed"] = trim_feed(fetcher.feed(pk))
                    work["feed_at"] = iso(now_fn())
                elif call == "content":
                    # a failed content read leaves the game's other reads and its
                    # last clip set alone: the page shows what the last read held
                    try:
                        work["content"] = sc.trim_content(fetcher.content(pk))
                        work["content_at"] = iso(now_fn())
                    except FetchError as e:
                        counts["content_fetch_failed"] = counts.get("content_fetch_failed", 0) + 1
                        log.warning("scores_job: content read for %s failed: %s", pk, e)
                    _gstate(state, pk)["content_epoch"] = now_fn().timestamp()
            except BudgetExhausted:
                ok = False
                rolled.append(pk)
                break
            except RateLimited as e:
                rl = e
                ok = False
                rolled.append(pk)
                break
            except FetchError as e:
                ok = False
                failed.add(pk)
                counts["game_fetch_failed"] = counts.get("game_fetch_failed", 0) + 1
                mark_game_failure(state, pk, now_fn(), f"{call}: {e}")
                break
        if any(k in work for k in ("wp", "box", "feed", "content")):
            work["pk"] = pk
            write_json_plain(work_path(paths, pk), work)
        gs = _gstate(state, pk)
        t = now_fn().timestamp()
        if "wp" in task["calls"] and work.get("wp_at") and ok:
            gs["wp_epoch"] = t
        if "box" in task["calls"] and work.get("box_at") and ok:
            gs["box_epoch"] = t
        if ok:
            gs.pop("fail_n", None)
            gs.pop("backoff_until", None)
            gs.pop("stale_since", None)
            gs.pop("last_error", None)
            gs["updated_epoch"] = t
            done.setdefault(pk, []).append(task)
    return {"done": done, "rolled": sorted(set(rolled)), "rate_limited": rl}


# --------------------------------------------------------------------------- #
# Building and writing the files
# --------------------------------------------------------------------------- #
def _strip_volatile(obj, keys=("generated_at", "updated_at", "rev")):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip_volatile(v, keys) for v in obj]
    return obj


def same_content(a, b, keys=("generated_at", "updated_at", "rev")) -> bool:
    if a is None or b is None:
        return False
    return sc.dumps(_strip_volatile(a, keys)) == sc.dumps(_strip_volatile(b, keys))


def people_map(state: dict) -> dict:
    return {int(k): v for k, v in (state.get("people") or {}).items()}


def parse_people(doc) -> dict:
    out = {}
    for p in (doc or {}).get("people") or []:
        if p.get("id") is None:
            continue
        hand = (p.get("pitchHand") or {}).get("code")
        split = None
        for s in p.get("stats") or []:
            if ((s.get("group") or {}).get("displayName") or "") != "pitching":
                continue
            splits = s.get("splits") or []
            total = [x for x in splits if "team" not in x]
            split = (total or splits or [None])[-1]
        stat = (split or {}).get("stat") or {}
        out[str(int(p["id"]))] = {"hand": hand, "w": stat.get("wins"), "l": stat.get("losses"), "era": stat.get("era")}
    return out


def clips_pending(g: dict, gs: dict, now: datetime) -> bool:
    """A missing clip may still post while the game is not final and within
    24 hours of the final (plan 6.5, F3)."""
    if not sc.is_final(g.get("status")):
        return True
    f = parse_stamp(gs.get("final_seen_at"))
    return f is None or now.timestamp() - f.timestamp() < sc.CLIP_PENDING_S


def build_game(g: dict, work: dict, served: dict, people: dict, gen: str, *, pending: bool = True,
               clip_log: dict | None = None) -> dict | None:
    season = sc._int(g.get("season"), 0) or sc._int(str(g.get("officialDate") or "")[:4], 0)
    lg = lg_for(served["constants"], season)
    if lg is None:
        log.warning("scores_job: no league constants were ever read; game %s keeps its schedule card",
                    g.get("gamePk"))
        return None
    return sc.build_game_file(g, work.get("wp"), work.get("box"), lg,
                              generated_at=gen, feed=work.get("feed"), people=people,
                              content=work.get("content"), clips_pending=pending, seen_at=work.get("content_at"),
                              clip_log=clip_log)


def content_due_at(wp, gf: dict) -> float | None:
    """The instant a live game's next content read is wanted early: 90 s after
    the end of the earliest top-five plate appearance that has no result clip
    (its `about.endTime`); None when every top-five play has one."""
    ends = {}
    for p in sc.complete_elements(wp):
        dt = parse_stamp((p.get("about") or {}).get("endTime"))
        if dt is not None:
            ends[sc._ab(p)] = dt.timestamp()
    want = [ends[b["ab"]] for b in gf.get("plays_big") or [] if not b.get("clip") and b["ab"] in ends]
    return (min(want) + CONTENT_AFTER_PA_S) if want else None


#: Hook for tests: a callable (gf) -> gf applied to each built game file.
GAME_FILE_HOOK = None


class Cycle:
    """One acting invocation's build-and-publish pass over the dates it touched."""

    def __init__(self, paths: dict, state: dict, served: dict, now_fn, *, action: str):
        self.paths, self.state, self.served, self.now_fn, self.action = paths, state, served, now_fn, action
        self.writer = Writer(paths["out"])
        self.gen = iso(now_fn())
        self.counts = {"files_written": 0, "files_refused": 0, "over_budget": 0, "game_fetch_failed": 0}
        self.refused_dates: dict = {}
        self.stale_games: dict = {}
        self.game_cards: dict = {}
        self.clips: dict = {}
        self._pre: dict | None = None

    def pre_ctx(self) -> dict:
        """The pregame reads, once per cycle and only when a Preview card needs them."""
        if self._pre is None:
            try:
                self._pre = pregame_context(self.state, self.served)
            except Exception as e:  # noqa: BLE001 - a bad served file never stops the scores
                log.warning("scores_job: pregame context unavailable: %s", e)
                self._pre = {}
        return self._pre

    # --- game files ---
    def game_file(self, g: dict) -> dict | None:
        """Build and write the game file of a live or final game from its work
        payloads; return the card the date file carries, or None when the game
        has no game file (no win probability yet)."""
        pk = int(g["gamePk"])
        gs = (self.state.get("games") or {}).get(str(pk)) or {}
        rel = f"games/{pk}.json"
        prev = self.writer.read(rel)
        if gs.get("frozen") and isinstance(prev, dict):
            return prev.get("card")
        if sc.is_final(g.get("status")) and not gs.get("final_built"):
            # the final reads have not landed yet: never build a final from a
            # live read; the date file carries the schedule's final card
            return None
        work = read_work(self.paths, pk)
        if not work.get("wp"):
            return prev.get("card") if isinstance(prev, dict) else None
        clip_log: dict = {}
        gf = build_game(g, work, self.served, people_map(self.state), self.gen,
                        pending=clips_pending(g, gs, self.now_fn()), clip_log=clip_log)
        if gf is None:
            return prev.get("card") if isinstance(prev, dict) else None
        if clip_log:
            self.clips[str(pk)] = clip_log
            if clip_log.get("new_media_host"):
                log.warning("scores_job: new_media_host %s on game %s", clip_log["new_media_host"], pk)
        gsw = _gstate(self.state, pk)
        if sc.game_state(g.get("status"))[0] in ("live", "delayed"):
            gsw["content_due_at"] = content_due_at(work.get("wp"), gf)
        else:
            gsw.pop("content_due_at", None)
        if GAME_FILE_HOOK is not None:
            gf = GAME_FILE_HOOK(gf)
        if isinstance(prev, dict) and same_content(gf, prev):
            return prev.get("card")
        res = self.writer.write(rel, "game", gf)
        self._count(res)
        if not res["ok"]:
            self.stale_games[pk] = gs.get("stale_since") or self.gen
            return prev.get("card") if isinstance(prev, dict) else None
        self.state.setdefault("game_season", {})[str(pk)] = sc._int(g.get("season"), 0)
        if gf["wp"].get("pregame_home") is not None:
            self.state.setdefault("pregame", {})[str(pk)] = [sc._int(g.get("season"), 0), gf["wp"]["pregame_home"]]
        return gf["card"]

    def _count(self, res: dict) -> None:
        if res.get("written"):
            self.counts["files_written"] += 1
        over = [m for r, m in (res.get("logged") or []) if r == "6"]
        if over:
            self.counts["over_budget"] += len(over)
            budget = sc.FILE_KINDS.get(res.get("kind"), {}).get("budget")
            self.counts.setdefault("over_budget_files", []).append(
                {"file": res["rel"], "bytes": res.get("bytes"), "budget": budget})
            log.warning("scores_job: over_budget %s %s bytes (budget %s)", res["rel"], res.get("bytes"), budget)
        name = res["rel"]
        rf = self.state.setdefault("refused_files", {})
        if not res["ok"]:
            self.counts["files_refused"] += 1
            self.state.setdefault("refusals", []).append(self.gen)
            entry = rf.setdefault(name, {"n": 0, "since": self.gen})
            entry["n"] += 1
            entry["last"] = self.gen
            entry["rule"] = "; ".join(f"{r}: {m}" for r, m in res["refused"][:3])
            log.warning("scores_job: refused %s: %s", name, entry["rule"])
        else:
            rf.pop(name, None)

    # --- date files ---
    def date_file(self, d: str, games: list[dict], schedule_all: list[dict]) -> None:
        rel = f"{d}.json"
        prev = self.writer.read(rel)
        prev_cards = {c.get("pk"): c for c in (prev or {}).get("games") or []} if isinstance(prev, dict) else {}
        cards, gfs = [], {}
        people = people_map(self.state)
        for g in games:
            pk = int(g["gamePk"])
            card = self.game_cards.get(pk)
            if card is None:
                card = sc.build_card(g, generated_at=self.gen, people=people)
            card = json.loads(json.dumps(card))
            if sc.pre_open(g):
                pre = sc.pre_block(g, card, self.pre_ctx())
                if pre:
                    card["pre"] = pre
            gs = (self.state.get("games") or {}).get(str(pk)) or {}
            card["stale_since"] = self.stale_games.get(pk) or gs.get("stale_since")
            old = prev_cards.get(pk)
            if old is not None and same_content(card, old, keys=("updated_at",)):
                card["updated_at"] = old.get("updated_at") or card["updated_at"]
            cards.append(card)
            gf = self.writer.read(f"games/{pk}.json")
            if isinstance(gf, dict):
                gfs[pk] = gf
        obj = sc.build_date_file(d, cards, gfs, generated_at=self.gen)
        if isinstance(prev, dict) and same_content(obj, prev, keys=("generated_at",)):
            self._catalog(d, prev, self.writer.disk_rev(rel))
            return
        shrink = sc.check_shrink(list(prev_cards.values()), cards, schedule_all) if prev_cards else []
        res = self.writer.write(rel, "date", obj, extra_refusals=shrink)
        self._count(res)
        if not res["ok"]:
            self.refused_dates[d] = self.gen
            for c in cards:
                self.stale_games.setdefault(c["pk"], self.gen)
            return
        self._catalog(d, obj, res["rev"])

    def _catalog(self, d: str, obj: dict, rev: str | None) -> None:
        season = str(d[:4])
        cards = obj.get("games") or []
        flags = sorted({k for c in cards for k, v in (c.get("flags") or {}).items() if v})
        types = sorted({c.get("type") for c in cards if c.get("type")})
        entry = {"d": d, "n": len(cards), "types": types, "rev": rev, "flags": flags}
        self.state.setdefault("catalog", {}).setdefault(season, {})[d] = entry
        # a date with a card still scheduled, pregame, delayed or live is not
        # final-complete; the week cycle rebuilds it once it is in the past
        opened = set(self.state.get("open_dates") or [])
        if any(c.get("state") in ("scheduled", "pregame", "delayed", "live") for c in cards):
            opened.add(d)
        else:
            opened.discard(d)
        self.state["open_dates"] = sorted(opened)

    # --- indexes and latest ---
    def season_index(self, season: str) -> str | None:
        cat = (self.state.get("catalog") or {}).get(season) or {}
        rel = f"index-{season}.json"
        obj = {"schema": sc.SCHEMA, "season": int(season),
               "dates": [cat[d] for d in sorted(cat)], "bracket": (self.state.get("bracket") or {}).get(str(season))}
        prev = self.writer.read(rel)
        if isinstance(prev, dict) and same_content(obj, prev, keys=()):
            return self.writer.disk_rev(rel)
        res = self.writer.write(rel, "season_index", obj)
        self._count(res)
        return res["rev"]

    def pregame_values(self) -> dict:
        """{value: count} of wp.pregame_home over the current season's game
        files, kept from the game files this job wrote (never read from
        data/win_expectancy.json, which has no pregame field)."""
        pre = self.state.get("pregame") or {}
        cur = current_season(self.state, self.now_fn())
        counts: dict = {}
        for pk, (season, v) in pre.items():
            if int(season) == cur and (self.paths["out"] / "games" / f"{pk}.json").exists():
                counts[str(v)] = counts.get(str(v), 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: int(kv[0])))

    def index(self) -> dict:
        seasons = []
        for season in sorted(self.state.get("catalog") or {}):
            rev = self.season_index(season)
            seasons.append({"season": int(season), "rev": rev,
                            "n_dates": len((self.state.get("catalog") or {}).get(season) or {})})
        embed, why = embed_status(self.paths["out"])
        self.state["embed"] = embed
        self.state["embed_reason"] = why
        obj = {"schema": sc.SCHEMA, "generated_at": self.gen, "seasons": seasons,
               "registry": self.served["registry"],
               "accuracy": {"mlb_wp": dict(self.served["accuracy"], pregame_values=self.pregame_values())},
               "rules": {"stars": {"rule": sc.STARS_RULE, "min_outs": sc.MIN_OUTS, "min_coverage": sc.MIN_COVERAGE,
                                   "first_star_winner": sc.FIRST_STAR_WINNER},
                         "plays": {"rule": sc.PLAYS_RULE, "min_swing": sc.MIN_SWING, "n": sc.N_BIG_PLAYS},
                         "video": {"embed": embed, "branch": sc.VIDEO_BRANCH, "video_hosts": list(sc.VIDEO_HOSTS),
                                   "caption_hosts": list(sc.CAPTION_HOSTS), "poster_host": sc.POSTER_HOST,
                                   "frame_host": sc.FRAME_HOST}},
               "copyright": self.state.get("copyright") or f"Copyright MLB Advanced Media, L.P. {sc.MLB_TERMS_URL}"}
        return obj

    def write_index(self) -> dict:
        obj = self.index()
        prev = self.writer.read("index.json")
        if isinstance(prev, dict) and same_content(obj, prev, keys=("generated_at",)):
            return {"ok": True, "rev": self.writer.disk_rev("index.json"), "obj": prev, "written": False}
        res = self.writer.write("index.json", "index", obj)
        self._count(res)
        res["obj"] = obj if res["ok"] else prev
        return res


def current_season(state: dict, now: datetime) -> int:
    cat = state.get("catalog") or {}
    seasons = [int(s) for s in cat if str(s).isdigit()]
    return max(seasons) if seasons else utc_date(now).year


def window_dates(now: datetime) -> list[str]:
    d = utc_date(now)
    return [(d + timedelta(days=i)).isoformat() for i in range(-1, 8)]


def build_latest(cyc: Cycle, *, action: str, job_state: str, next_by_iso: str, index_rev: str | None,
                 rows: list[dict], now: datetime) -> dict:
    st = cyc.state
    w = cyc.writer
    window = {}
    live_list = []
    for d in window_dates(now):
        doc = w.read(f"{d}.json")
        cards = (doc or {}).get("games") or [] if isinstance(doc, dict) else []
        cnt = {"live": 0, "final": 0, "pre": 0, "off": 0}
        stale = cyc.refused_dates.get(d)
        clips_of = clips_matched = 0
        for c in cards:
            s = c.get("state")
            if s in ("live", "delayed"):
                cnt["live"] += 1
                live_list.append({"pk": c["pk"], "date": d})
            elif s == "final":
                cnt["final"] += 1
            elif s in ("scheduled", "pregame"):
                cnt["pre"] += 1
            else:
                cnt["off"] += 1
            if c.get("stale_since"):
                stale = min(stale or c["stale_since"], c["stale_since"])
            gf = w.read(f"games/{c['pk']}.json")
            for b in ((gf or {}).get("plays_big") or []) if isinstance(gf, dict) else []:
                clips_of += 1
                clips_matched += 1 if b.get("clip") else 0
        window[d] = {"rev": w.disk_rev(f"{d}.json") if cards else None, "n": len(cards), **cnt,
                     "clips_matched": clips_matched, "clips_of": clips_of, "stale_since": stale}
    errors = _recent(st.get("errors") or [], now)
    refusals = _recent(st.get("refusals") or [], now)
    st["errors"], st["refusals"] = errors, refusals
    return {"schema": sc.SCHEMA, "generated_at": cyc.gen,
            "job": {"action": action, "state": job_state, "next_by": next_by_iso, "last_ok_at": st.get("last_ok_at"),
                    "down_after_s": DOWN_AFTER_S, "poll_live_s": POLL_LIVE_S, "poll_idle_s": POLL_IDLE_S,
                    "errors_24h": len(errors), "refusals_24h": len(refusals)},
            "index_rev": index_rev, "today": today_date(rows, now, st), "next_game_date": next_game_date(rows, now, st),
            "window": window, "live": live_list}


def _recent(stamps: list, now: datetime) -> list:
    cut = now.timestamp() - 86400
    out = []
    for s in stamps:
        dt = parse_stamp(s)
        if dt is not None and dt.timestamp() >= cut:
            out.append(s)
    return out[-500:]


def today_date(rows: list[dict], now: datetime, state: dict) -> str | None:
    """The page's suggested date, read from officialDate values and never from
    a clock: the smallest date among Live games; else that of a game Final in
    the last 3 hours; else that of the next Preview game; else the last date
    with games."""
    live = [r["date"] for r in rows if r.get("state") in ("live", "delayed") and r.get("date")]
    if live:
        return min(live)
    t = now.timestamp()
    fin = [r["date"] for r in rows if r.get("state") == "final" and parse_stamp(r.get("final_seen_at"))
           and t - parse_stamp(r["final_seen_at"]).timestamp() <= 3 * 3600]
    if fin:
        return max(fin)
    pre = sorted((r.get("start") or "", r["date"]) for r in rows
                 if r.get("state") in ("scheduled", "pregame") and r.get("date") and (_start_epoch(r) or 0) >= t - 3600)
    if pre:
        return pre[0][1]
    dates = [r["date"] for r in rows if r.get("date")]
    if dates:
        return max(dates)
    cat = state.get("catalog") or {}
    alld = [d for s in cat.values() for d in s]
    return max(alld) if alld else None


def next_game_date(rows: list[dict], now: datetime, state: dict) -> str | None:
    t = now.timestamp()
    pre = sorted(r["date"] for r in rows if r.get("state") in ("scheduled", "pregame", "delayed")
                 and r.get("date") and (_start_epoch(r) or 0) >= t - 3600)
    if pre:
        return pre[0]
    return state.get("next_game_date")


# --------------------------------------------------------------------------- #
# Telemetry
# --------------------------------------------------------------------------- #
def write_heartbeat(paths: dict, result: dict, now: datetime) -> None:
    try:
        write_json_plain(paths["heartbeat"], {
            "last_run_utc": iso(now), "action": result.get("action"), "state": result.get("job_state"),
            "reason": result.get("reason"), "exit": result.get("exit"), "requests": result.get("requests", 0),
            "counts": result.get("counts"), "out": str(paths["out"]), "last_publish": result.get("last_publish"),
            "scores_live": bool(sc.SCORES_LIVE)})
    except Exception:                                     # noqa: BLE001
        log.warning("scores_job: could not write the heartbeat", exc_info=True)


def append_runlog(paths: dict, result: dict, now: datetime) -> None:
    try:
        p = paths["runlog_dir"] / f"runlog-{utc_date(now).isoformat()}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {"at": iso(now), "action": result.get("action"), "exit": result.get("exit"),
               "requests": result.get("requests", 0), "counts": result.get("counts"),
               "reason": (result.get("reason") or "")[:300]}
        if result.get("clips"):
            # per game (plan 6.6): clips matched, with captions, rows at F1
            # and F3 among the biggest plays, and any new_media_host
            rec["clips"] = result["clips"]
        line = json.dumps(rec, separators=(",", ":"), sort_keys=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:                                     # noqa: BLE001
        log.warning("scores_job: could not append the run log", exc_info=True)


def read_heartbeat(paths: dict | None = None):
    return read_json((paths or resolve_paths())["heartbeat"])


def load_state(paths: dict) -> dict:
    st = read_json(paths["state"])
    return st if isinstance(st, dict) else {}


def save_state(paths: dict, state: dict) -> None:
    write_json_plain(paths["state"], state)


# --------------------------------------------------------------------------- #
# Pruning (SC-KEEP (a)): dates every season; game and work files two seasons;
# run logs 14 days. OUT/standings/ is never touched.
# --------------------------------------------------------------------------- #
def prune(paths: dict, state: dict, now: datetime) -> dict:
    cur = current_season(state, now)
    removed = {"games": 0, "work": 0, "runlogs": 0}
    gs_map = state.get("game_season") or {}
    gdir = paths["out"] / "games"
    for p in sorted(gdir.glob("*.json")) if gdir.exists() else []:
        season = gs_map.get(p.stem)
        if season is None:
            doc = read_json(p)
            season = sc._int(str((((doc or {}).get("card") or {}).get("start")) or "")[:4], 0) or None
        if season and int(season) < cur - 1:
            p.unlink(missing_ok=True)
            gs_map.pop(p.stem, None)
            (state.get("pregame") or {}).pop(p.stem, None)
            removed["games"] += 1
    wdir = paths["work"]
    for p in sorted(wdir.glob("*.json")) if wdir.exists() else []:
        doc = read_json(p) or {}
        season = sc._int(doc.get("season"), 0) or gs_map.get(p.stem)
        if season and int(season) < cur - 1:
            p.unlink(missing_ok=True)
            removed["work"] += 1
    cut = (utc_date(now) - timedelta(days=RUNLOG_KEEP_DAYS)).isoformat()
    for p in paths["runlog_dir"].glob("runlog-*.jsonl"):
        if p.stem[len("runlog-"):] < cut:
            p.unlink(missing_ok=True)
            removed["runlogs"] += 1
    for pk, g in list((state.get("games") or {}).items()):
        if g.get("frozen") and str(pk) not in gs_map and not (gdir / f"{pk}.json").exists():
            state["games"].pop(pk, None)
    return removed


def rebuild_catalog(paths: dict, state: dict) -> None:
    """When state.json lost its catalog or its pregame map, read the files on
    disk once (date files for the catalog, game files for the pregame values
    and their seasons)."""
    out = paths["out"]
    if "pregame" not in state:
        pre, seasons = {}, {}
        gdir = out / "games"
        for p in sorted(gdir.glob("*.json")) if gdir.exists() else []:
            doc = read_json(p)
            if not isinstance(doc, dict):
                continue
            season = sc._int(str(((doc.get("card") or {}).get("start")) or "")[:4], 0)
            seasons[p.stem] = season
            v = (doc.get("wp") or {}).get("pregame_home")
            if v is not None:
                pre[p.stem] = [season, v]
        state["pregame"] = pre
        state.setdefault("game_season", {}).update({k: v for k, v in seasons.items() if v})
    if state.get("catalog"):
        return
    cat: dict = {}
    for p in sorted(out.glob("*.json")) if out.exists() else []:
        if not re.match(r"^\d{4}-\d{2}-\d{2}\.json$", p.name):
            continue
        doc = read_json(p)
        if not isinstance(doc, dict):
            continue
        cards = doc.get("games") or []
        cat.setdefault(p.stem[:4], {})[p.stem] = {
            "d": p.stem, "n": len(cards), "types": sorted({c.get("type") for c in cards if c.get("type")}),
            "rev": sc.rev_of(p.read_bytes()),
            "flags": sorted({k for c in cards for k, v in (c.get("flags") or {}).items() if v})}
    if cat:
        state["catalog"] = cat


def freeze_game(paths: dict, state: dict, pk: int) -> None:
    """After finalize the game file never changes; the work file drops its
    payloads so the store stays small."""
    gs = _gstate(state, pk)
    gs["frozen"] = True
    w = read_work(paths, pk)
    keep = {k: w.get(k) for k in ("pk", "date", "season", "wp_at", "box_at", "feed_at", "content_at")
            if w.get(k) is not None}
    keep["frozen"] = True
    write_json_plain(work_path(paths, pk), keep)


# --------------------------------------------------------------------------- #
# One acting cycle
# --------------------------------------------------------------------------- #
def bracket_due(state: dict, games: list[dict], d0: date) -> int | None:
    """The season whose bracket this idle cycle reads, or None. Due from the
    first postseason date to the last: a postseason game (BRACKET_TYPES) in
    this cycle's schedule dated today or earlier, or today inside the last
    block's first date to its last date plus one day (a night game ends after
    midnight UTC). Never again once the block reads `done` (the World Series
    is over and its final state is on file)."""
    season = d0.year
    have = (state.get("bracket") or {}).get(str(season)) or {}
    if have.get("done"):
        return None
    today = d0.isoformat()
    if any(g.get("gameType") in BRACKET_TYPES and str(g.get("officialDate") or "9999") <= today for g in games):
        return season
    first, last = have.get("first"), have.get("last")
    if first and last:
        try:
            if first <= today <= (date.fromisoformat(last) + timedelta(days=1)).isoformat():
                return season
        except ValueError:
            return None
    return None


def act(decision: dict, paths: dict, state: dict, slate: dict | None, fetcher: Fetcher, now_fn, *,
        only_date: str | None = None) -> dict:
    """Fetch, build, validate and write for one acting cycle. Returns the
    result dict main() reports."""
    now = now_fn()
    cycle = decision.get("cycle") or "idle"
    tick = int(decision.get("tick") or tick_of(now.timestamp()))
    result = {"action": decision.get("action"), "reason": decision.get("reason"), "exit": 0, "counts": {}}
    d0 = utc_date(now)
    if only_date:
        span = (only_date, only_date)
    elif cycle in ("week", "offseason"):
        span = ((d0 - timedelta(days=1)).isoformat(), (d0 + timedelta(days=7)).isoformat())
    else:
        span = ((d0 - timedelta(days=1)).isoformat(), (d0 + timedelta(days=1)).isoformat())
    served = served_blocks(state, current_season=d0.year)

    # 1. the schedule. A failure rewrites only latest.json and backs off.
    try:
        sched = fetcher.schedule(*span)
    except (FetchError, RateLimited, BudgetExhausted) as e:
        rate = isinstance(e, RateLimited)
        mark_backoff(state, now, e.retry_after if rate else None)
        state.setdefault("errors", []).append(iso(now))
        cyc = Cycle(paths, state, served, now_fn, action="fetch_failed")
        rows = (slate or {}).get("games") or []
        latest = build_latest(cyc, action="fetch_failed", job_state="backoff" if rate else "degraded",
                              next_by_iso=iso(float(state["backoff_until"]) + NEXT_BY_GRACE_S),
                              index_rev=cyc.writer.disk_rev("index.json"), rows=rows, now=now)
        res = cyc.writer.write("latest.json", "latest", latest)
        result.update(action="fetch_failed", job_state=latest["job"]["state"], exit=2,
                      reason=f"the schedule call for {span[0]}..{span[1]} failed ({e}); backoff until "
                             f"{iso(float(state['backoff_until']))}",
                      counts={"latest_written": bool(res["ok"])})
        return result
    games = schedule_games(sched)
    if sched.get("copyright"):
        state["copyright"] = sc.normalize_text(sched["copyright"])
    slate = merge_slate(slate, games, span, now)
    all_games = list(games)

    # 2. people (week cycles; idle cycles when a probable in the window changed)
    probable_ids = sorted({i for r in slate["games"] for i in (r.get("probables") or [])})
    want_people = cycle == "week" or (cycle == "idle" and probable_ids != sorted(state.get("people_ids") or []))
    if want_people and probable_ids and fetcher.limiter.can_start():
        try:
            state["people"] = parse_people(fetcher.people(probable_ids))
            state["people_ids"] = probable_ids
        except (FetchError, BudgetExhausted):
            pass
        except RateLimited as e:
            mark_backoff(state, now, e.retry_after)

    # 3. week cycle: finalize yesterday, queue rebuilds; offseason: the next game date
    if cycle == "week" and not only_date:
        yday = (d0 - timedelta(days=1)).isoformat()
        fin = sorted({int(g["gamePk"]) for g in games if g.get("officialDate") == yday and sc.is_final(g.get("status"))
                      and not ((state.get("games") or {}).get(str(int(g["gamePk"]))) or {}).get("frozen")})
        pend = state.setdefault("pending", {})
        pend["finalize"] = sorted(set(pend.get("finalize") or []) | set(fin))
        pend["rebuild"] = sorted(set(pend.get("rebuild") or []) | set(rebuild_candidates(state, d0)))[-REBUILD_MAX_DATES:]
        state["week_date"] = d0.isoformat()
    if cycle == "offseason" or (cycle == "week" and not any(sc.game_state(g.get("status"))[0] in ("scheduled", "pregame")
                                                            for g in games)):
        if fetcher.limiter.can_start():
            try:
                far = fetcher.schedule(d0.isoformat(), (d0 + timedelta(days=200)).isoformat(), hydrate=False)
                dates = sorted(d.get("date") for d in far.get("dates") or [] if d.get("games"))
                state["next_game_date"] = dates[0] if dates else None
            except (FetchError, BudgetExhausted):
                pass
            except RateLimited as e:
                mark_backoff(state, now, e.retry_after)

    # 3b. the October bracket: idle cycles only, one call; a failed read keeps
    # the last block (the season index carries it either way)
    bseason = bracket_due(state, games, d0) if cycle == "idle" and not only_date else None
    if (bseason is not None and fetcher.limiter.can_start()
            and float(state.get("backoff_until") or 0) <= now.timestamp()):
        try:
            block = sc.build_bracket(fetcher.postseason_series(bseason), season=bseason)
            if block is not None:
                state.setdefault("bracket", {})[str(bseason)] = block
        except (FetchError, BudgetExhausted):
            pass
        except RateLimited as e:
            mark_backoff(state, now, e.retry_after)

    # 4. rebuild queued earlier dates (each: one schedule call, then its finals)
    rebuild_games: list = []
    pend = state.setdefault("pending", {})
    for d in list(pend.get("rebuild") or []):
        if float(state.get("backoff_until") or 0) > now.timestamp() or not fetcher.limiter.can_start():
            break
        try:
            more = schedule_games(fetcher.schedule(d, d))
        except (FetchError, BudgetExhausted):
            break
        except RateLimited as e:
            mark_backoff(state, now, e.retry_after)
            break
        rebuild_games.extend(more)
        pend["rebuild"] = [x for x in pend["rebuild"] if x != d]
        state.setdefault("known_dates", {})[d] = len(more)
        tries = state.setdefault("rebuild_tries", {})
        tries[d] = int(tries.get(d) or 0) + 1
        # a rebuilt date's finals are read once more and frozen
        pend["finalize"] = sorted(set(pend.get("finalize") or []) | {
            int(g["gamePk"]) for g in more if sc.is_final(g.get("status"))
            and not ((state.get("games") or {}).get(str(int(g["gamePk"]))) or {}).get("frozen")})
    all_games.extend(rebuild_games)
    by_pk = {int(g["gamePk"]): g for g in all_games}
    for g in all_games:
        gs = _gstate(state, int(g["gamePk"]))
        gs["date"] = g.get("officialDate")
        if sc.is_final(g.get("status")):
            row = next((r for r in slate["games"] if r["pk"] == int(g["gamePk"])), None)
            if row and row.get("final_seen_at") and not gs.get("final_seen_at"):
                gs["final_seen_at"] = row["final_seen_at"]
            elif not gs.get("final_seen_at"):
                gs["final_seen_at"] = iso(now)
    # a finalize whose date left this cycle's span goes back through a rebuild;
    # a game that keeps failing leaves the queue (the week cycle retries its date)
    keep_fin = []
    for pk in pend.get("finalize") or []:
        gs = (state.get("games") or {}).get(str(int(pk))) or {}
        if int(gs.get("fail_n") or 0) >= GIVE_UP_FAILS:
            continue
        if int(pk) not in by_pk:
            if gs.get("date") and gs["date"] >= HISTORY_FLOOR:
                pend["rebuild"] = sorted(set(pend.get("rebuild") or []) | {gs["date"]})
            continue
        keep_fin.append(int(pk))
    pend["finalize"] = sorted(set(keep_fin))

    # 5. per-game calls inside the limiter
    tasks = [] if float(state.get("backoff_until") or 0) > now.timestamp() else plan_tasks(all_games, state, now, cycle, tick)
    counts = {"game_fetch_failed": 0}
    ran = run_tasks(tasks, fetcher, state, paths, now_fn, counts)
    if ran["rate_limited"] is not None:
        mark_backoff(state, now, ran["rate_limited"].retry_after)
    else:
        # job-level backoff when most of the cycle's calls returned 429 or 5xx
        bad = [s for s in fetcher.statuses if s == 429 or s >= 500]
        if len(fetcher.statuses) >= 4 and len(bad) * 2 > len(fetcher.statuses):
            mark_backoff(state, now, None)
    pend["rollover"] = ran["rolled"]
    queued = {int(x) for x in pend.get("finalize") or []}
    finalized: set = set()
    for pk, done_tasks in ran["done"].items():
        gs = _gstate(state, pk)
        g = by_pk.get(pk) or {}
        work = read_work(paths, pk)
        work.update({"date": g.get("officialDate"), "season": sc._int(g.get("season"), 0)})
        write_json_plain(work_path(paths, pk), work)
        for task in done_tasks:
            why = task["why"]
            if why == "final" and pk in queued:
                why = "finalize"              # the first final read of a queued game is its finalize
            if "wp" in task["calls"]:
                gs["wp_hash"] = state_hash(g)
            if why in ("final", "finalize"):
                gs["final_built"] = True
                f = parse_stamp(gs.get("final_seen_at"))
                if f is not None and now.timestamp() - f.timestamp() >= max(FINAL_REFRESH_MIN) * 60:
                    gs["refreshed"] = sorted(FINAL_REFRESH_MIN)   # an old final needs no +60 or +180 reread
            if why.startswith("final_refresh"):
                gs["refreshed"] = sorted(set(gs.get("refreshed") or []) | {task["minutes"]})
            if why == "finalize":
                finalized.add(pk)
                pend["finalize"] = [x for x in pend.get("finalize") or [] if int(x) != pk]
    if counts["game_fetch_failed"]:
        state.setdefault("errors", []).extend([iso(now)] * counts["game_fetch_failed"])

    # 6. game files, date files (games, then date), season index, index, latest
    cyc = Cycle(paths, state, served, now_fn, action=decision.get("action") or cycle)
    rebuild_catalog(paths, state)
    for g in all_games:
        st_, _ = sc.game_state(g.get("status"))
        if st_ in ("live", "delayed", "final", "suspended"):
            card = cyc.game_file(g)
            if card is not None:
                cyc.game_cards[int(g["gamePk"])] = card
    # finalized games freeze only after their game file is on disk
    for pk in sorted(finalized):
        if (paths["out"] / "games" / f"{pk}.json").exists() and pk not in cyc.stale_games:
            freeze_game(paths, state, pk)
    by_date: dict = {}
    for g in all_games:
        by_date.setdefault(g.get("officialDate"), {})[int(g["gamePk"])] = g
    dates_written = []
    for d in sorted(x for x in by_date if x):
        cyc.date_file(d, sorted(by_date[d].values(), key=lambda g: (g.get("gameDate") or "", g["gamePk"])), all_games)
        dates_written.append(d)
    idx = cyc.write_index()
    for c in ("files_written", "files_refused", "over_budget"):
        counts[c] = cyc.counts[c]
    publish_failed = any(r.get("publish_failed") for r in cyc.writer.results.values())
    job_state = "ok" if live_games(slate["games"], now) else "idle"
    if float(state.get("backoff_until") or 0) > now.timestamp():
        job_state = "backoff"
    if not idx["ok"]:
        job_state = "degraded"
    nb_tick = tick
    if decision.get("cycle") == "live" or live_games(slate["games"], now):
        state["last_live_tick"] = tick
    state["last_cycle_tick"] = tick
    if job_state in ("ok", "idle"):
        state["last_ok_at"] = cyc.gen
        state["backoff_n"] = 0
        state.pop("backoff_until", None)
    nb = next_by(nb_tick, slate["games"], now, state)
    if job_state == "backoff":
        nb = iso(max(parse_stamp(nb).timestamp(), float(state["backoff_until"]) + NEXT_BY_GRACE_S))
    latest = build_latest(cyc, action=decision.get("action") or cycle, job_state=job_state, next_by_iso=nb,
                          index_rev=idx.get("rev"), rows=slate["games"], now=now)
    lres = cyc.writer.write("latest.json", "latest", latest)
    cyc._count(lres)
    publish_failed = publish_failed or bool(lres.get("publish_failed"))

    # 7. rule 11: every rev in latest.json and index.json equals the bytes on disk
    mism = verify_revs(cyc.writer) if lres["ok"] else []
    if cycle == "week" and not only_date:
        result["pruned"] = prune(paths, state, now)
    write_json_plain(paths["slate"], slate)
    counts["requests"] = fetcher.limiter.n
    counts["rolled_over"] = len(ran["rolled"])
    result.update(counts=counts, job_state=latest["job"]["state"], dates=dates_written,
                  requests=fetcher.limiter.n, last_publish=cyc.gen if lres["ok"] else None)
    if cyc.clips:
        result["clips"] = cyc.clips
    if not lres["ok"] or not idx["ok"]:
        result.update(action="refused", exit=2,
                      reason=f"latest.json or index.json refused: {(lres.get('refused') or idx.get('refused'))[:2]}")
    elif publish_failed or mism:
        result.update(action="publish_failed", exit=2, reason=f"publish failed: {mism or 'replace_busy'}")
    else:
        result["reason"] = (f"{decision.get('reason')}; {len(dates_written)} date(s), "
                            f"{counts['files_written']} file(s) written, {counts['files_refused']} refused, "
                            f"{fetcher.limiter.n} request(s), {len(ran['rolled'])} game(s) rolled over")
    return result


def verify_revs(writer: Writer) -> list[str]:
    latest = writer.read("latest.json") or {}
    index = writer.read("index.json") or {}
    bad = []
    if latest.get("index_rev") != writer.disk_rev("index.json"):
        bad.append("index_rev")
    for d, w in (latest.get("window") or {}).items():
        if w.get("rev") is not None and w["rev"] != writer.disk_rev(f"{d}.json"):
            bad.append(d)
    for s in index.get("seasons") or []:
        if s.get("rev") != writer.disk_rev(f"index-{s['season']}.json"):
            bad.append(f"index-{s['season']}")
    return bad


def rebuild_candidates(state: dict, d0: date) -> list[str]:
    """Earlier dates (before yesterday, never before HISTORY_FLOOR) whose date
    file is missing or not final-complete: a card still live or pregame, or a
    final game that never froze. Newest first, at most five."""
    cut = (d0 - timedelta(days=1)).isoformat()
    out = set()
    for g in (state.get("games") or {}).values():
        w = g.get("date")
        if w and HISTORY_FLOOR <= w < cut and g.get("final_built") and not g.get("frozen") \
                and int(g.get("fail_n") or 0) < GIVE_UP_FAILS:
            out.add(w)
    for d in state.get("open_dates") or []:
        if HISTORY_FLOOR <= d < cut:
            out.add(d)
    for d, n in (state.get("known_dates") or {}).items():
        if HISTORY_FLOOR <= d < cut and n and d not in ((state.get("catalog") or {}).get(d[:4]) or {}):
            out.add(d)
    tries = state.get("rebuild_tries") or {}
    out = {d for d in out if int(tries.get(d) or 0) < REBUILD_MAX_TRIES}
    return sorted(out, reverse=True)[:REBUILD_MAX_DATES]


# --------------------------------------------------------------------------- #
# --backfill A:B (a hand run; refuses 06:00 to 11:00 UTC and while a game is live)
# --------------------------------------------------------------------------- #
def cached_wp_ok(pk: int, game: dict):
    """A cached `.cache/win_prob/<pk>.json` only when its last element is
    complete and its last result score equals the final score in that date's
    schedule; else None. Opened read-only, never through the house getter."""
    p = HOUSE_WP_CACHE / f"{int(pk)}.json"
    doc = read_json(p)
    if doc is None:
        return None
    els = sc.elements_of(doc)
    if not els:
        return None
    last = els[-1]
    if not (last.get("about") or {}).get("isComplete"):
        return None
    res = last.get("result") or {}
    teams = game.get("teams") or {}
    ls = ((game.get("linescore") or {}).get("teams")) or {}
    away = (ls.get("away") or {}).get("runs", (teams.get("away") or {}).get("score"))
    home = (ls.get("home") or {}).get("runs", (teams.get("home") or {}).get("score"))
    if away is None or home is None or res.get("awayScore") != away or res.get("homeScore") != home:
        return None
    return doc


def cached_feed_ok(pk: int):
    """A cached `.cache/game_feeds/<pk>.json` only when its own status is final."""
    doc = read_json(HOUSE_FEED_CACHE / f"{int(pk)}.json")
    if not isinstance(doc, dict):
        return None
    status = (doc.get("gameData") or {}).get("status")
    return doc if sc.is_final(status) else None


def backfill_refusal(a: str, b: str, now: datetime, slate: dict | None) -> str | None:
    if a < HISTORY_FLOOR:
        return f"{a} is before HISTORY_FLOOR {HISTORY_FLOOR} (SC-HISTORY (a))"
    if b < a:
        return f"the range {a}:{b} runs backwards"
    if b >= utc_date(now).isoformat():
        return f"{b} is not a past date; the cron cycles own today and the window ahead"
    lo, hi = BACKFILL_REFUSE_UTC_HOURS
    if lo <= now.hour < hi:
        return f"it is {now.hour:02d}:{now.minute:02d} UTC, inside the {lo:02d}:00 to {hi:02d}:00 UTC nightly window"
    fetched = parse_stamp((slate or {}).get("fetched_at"))
    fresh = fetched is not None and now.timestamp() - fetched.timestamp() <= BACKFILL_SLATE_TRUST_S
    live = live_games((slate or {}).get("games") or [], now) if fresh else []
    if live:
        return f"{len(live)} game(s) live or within 20 minutes of first pitch; the live cycles come first"
    return None


def backfill(a: str, b: str, *, paths: dict, now_fn=_utcnow, adapter=None, lock: JobLock | None = None,
             clock=time.monotonic, sleep=time.sleep) -> dict:
    now = now_fn()
    slate = read_json(paths["slate"])
    why = backfill_refusal(a, b, now, slate)
    if why:
        return {"action": "backfill_refused", "exit": 2, "reason": why}
    state = load_state(paths)
    limiter = Limiter(max_requests=10 ** 9, run_deadline_s=10 ** 9, last_start_s=10 ** 9, clock=clock, sleep=sleep)
    fetcher = Fetcher(limiter, adapter)
    served = served_blocks(state, current_season=int(a[:4]))
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    counts = {"dates": 0, "games": 0, "wp_cached": 0, "feed_cached": 0, "failed": 0}
    released_at = 0

    def maybe_release():
        nonlocal released_at, state
        if lock is None or limiter.n - released_at < BACKFILL_RELEASE_EVERY:
            return
        save_state(paths, state)
        lock.release()
        sleep(1.0)
        for _ in range(600):
            if lock.acquire():
                break
            sleep(1.0)
        else:
            raise RuntimeError("could not reacquire the job lock")
        state = load_state(paths)
        released_at = limiter.n

    cur = da
    try:
        while cur <= db:
            end = min(db, cur + timedelta(days=BACKFILL_CHUNK_DAYS - 1))
            sched = fetcher.schedule(cur.isoformat(), end.isoformat())
            if sched.get("copyright"):
                state["copyright"] = sc.normalize_text(sched["copyright"])
            games = schedule_games(sched)
            for g in games:
                pk = int(g["gamePk"])
                if not sc.is_final(g.get("status")) or ((state.get("games") or {}).get(str(pk)) or {}).get("frozen"):
                    continue
                maybe_release()
                work = {"pk": pk, "date": g.get("officialDate"), "season": sc._int(g.get("season"), 0)}
                try:
                    wp = cached_wp_ok(pk, g)
                    if wp is not None:
                        counts["wp_cached"] += 1
                    else:
                        wp = fetcher.win_probability(pk)
                    feed = cached_feed_ok(pk)
                    if feed is not None:
                        counts["feed_cached"] += 1
                    else:
                        feed = fetcher.feed(pk)
                    work.update(wp=wp, box=fetcher.boxscore(pk), feed=trim_feed(feed),
                                wp_at=iso(now_fn()), box_at=iso(now_fn()), feed_at=iso(now_fn()))
                    # the game's clips (SCORES_4a): a failed content read leaves
                    # the game without clips, never without its file
                    try:
                        work.update(content=sc.trim_content(fetcher.content(pk)), content_at=iso(now_fn()))
                    except FetchError as e:
                        counts["content_failed"] = counts.get("content_failed", 0) + 1
                        log.warning("scores_job: backfill content read for %s failed: %s", pk, e)
                except FetchError as e:
                    counts["failed"] += 1
                    mark_game_failure(state, pk, now_fn(), str(e))
                    continue
                write_json_plain(work_path(paths, pk), work)
                gs = _gstate(state, pk)
                gs.update(final_built=True, date=g.get("officialDate"), refreshed=sorted(FINAL_REFRESH_MIN))
                gs.setdefault("final_seen_at", iso(now_fn()))
                counts["games"] += 1
            served = served_blocks(state, current_season=int(a[:4]))
            cyc = Cycle(paths, state, served, now_fn, action="backfill")
            rebuild_catalog(paths, state)
            by_date: dict = {}
            for g in games:
                card = cyc.game_file(g) if sc.is_final(g.get("status")) else None
                if card is not None:
                    cyc.game_cards[int(g["gamePk"])] = card
                by_date.setdefault(g.get("officialDate"), []).append(g)
            for g in games:
                pk = int(g["gamePk"])
                if sc.is_final(g.get("status")) and (paths["out"] / "games" / f"{pk}.json").exists() \
                        and pk not in cyc.stale_games:
                    freeze_game(paths, state, pk)
            for d in sorted(x for x in by_date if x):
                cyc.date_file(d, sorted(by_date[d], key=lambda g: (g.get("gameDate") or "", g["gamePk"])), games)
                state.setdefault("known_dates", {})[d] = len(by_date[d])
                counts["dates"] += 1
            idx = cyc.write_index()
            # latest.json names index.json's rev, so it follows every index write
            prev = cyc.writer.read("latest.json") or {}
            pjob = prev.get("job") or {}
            rows = (read_json(paths["slate"]) or {}).get("games") or []
            nowb = now_fn()
            latest = build_latest(cyc, action="backfill", job_state=pjob.get("state") or "idle",
                                  next_by_iso=pjob.get("next_by") or next_by(tick_of(nowb.timestamp()), rows, nowb, state),
                                  index_rev=idx.get("rev"), rows=rows, now=nowb)
            cyc._count(cyc.writer.write("latest.json", "latest", latest))
            save_state(paths, state)
            cur = end + timedelta(days=1)
    except RateLimited as e:
        mark_backoff(state, now_fn(), e.retry_after)
        save_state(paths, state)
        return {"action": "backfill_backoff", "exit": 2, "counts": counts, "requests": limiter.n,
                "reason": f"rate limited ({e}); resume from {cur.isoformat()} after {iso(float(state['backoff_until']))}"}
    except FetchError as e:
        save_state(paths, state)
        return {"action": "fetch_failed", "exit": 2, "counts": counts, "requests": limiter.n,
                "reason": f"the schedule call failed ({e}); resume from {cur.isoformat()}"}
    return {"action": "backfill", "exit": 0, "counts": counts, "requests": limiter.n,
            "reason": f"backfilled {a}..{b}: {counts['dates']} date(s), {counts['games']} final game(s), "
                      f"{counts['wp_cached']} cached win probability file(s), {counts['feed_cached']} cached feed(s)"}


# --------------------------------------------------------------------------- #
# The invocation
# --------------------------------------------------------------------------- #
def run(*, start: float | None = None, now_fn=_utcnow, adapter=None, jitter: bool = False,
        sleep=time.sleep, clock=time.monotonic, only_date: str | None = None, dry_run: bool = False) -> dict:
    """One invocation: bad_out, epoch hold, lock, jitter, decide, act. Always
    stamps the heartbeat and one run-log line (except under bad_out, where the
    store itself is not trusted, and under --dry-run, which writes nothing)."""
    start = time.time() if start is None else start
    tick = tick_of(start)
    paths = resolve_paths()
    why = bad_out(paths)
    if why:
        return {"action": "bad_out", "exit": 2, "reason": why}
    hold, hold_why = epoch_hold()
    if hold:
        res = {"action": "epoch_hold", "exit": 0, "reason": hold_why}
        if not dry_run:
            write_heartbeat(paths, res, now_fn())
            append_runlog(paths, res, now_fn())
        return res
    if dry_run:
        state, slate = load_state(paths), read_json(paths["slate"])
        d = decide(now_fn(), slate, state, tick=tick, embed=embed_effective(paths["out"]))
        plan = []
        if d["acts"]:
            rows = (slate or {}).get("games") or []
            plan = ["schedule"] + [f"{t['why']}:{t['pk']}:{'+'.join(t['calls'])}" for t in
                                   plan_tasks_from_rows(rows, state, now_fn())]
        return {"action": d["action"], "exit": 0, "reason": d["reason"], "plan": plan, "decision": d}
    lock = JobLock(paths["lock"])
    if not lock.acquire():
        res = {"action": "overlap", "exit": 0, "reason": "another invocation holds the job lock"}
        write_heartbeat(paths, res, now_fn())
        append_runlog(paths, res, now_fn())
        return res
    try:
        if jitter:
            sleep(random.uniform(0, JITTER_MAX_S))
        state, slate = load_state(paths), read_json(paths["slate"])
        now = now_fn()
        if only_date:
            d = {"acts": True, "action": "date", "cycle": "date", "tick": tick, "reason": f"--date {only_date}"}
        else:
            d = decide(now, slate, state, tick=tick, embed=embed_effective(paths["out"]))
        if not d["acts"]:
            res = {"action": d["action"], "exit": 0, "reason": d["reason"]}
        else:
            fetcher = Fetcher(Limiter(clock=clock, sleep=sleep), adapter)
            try:
                res = act(d, paths, state, slate, fetcher, now_fn, only_date=only_date)
            finally:
                save_state(paths, state)
        write_heartbeat(paths, res, now_fn())
        append_runlog(paths, res, now_fn())
        return res
    finally:
        lock.release()


def plan_tasks_from_rows(rows: list[dict], state: dict, now: datetime) -> list[dict]:
    """--dry-run's view of the per-game calls, from the slate rows alone."""
    out = []
    t = now.timestamp()
    for r in rows:
        gs = (state.get("games") or {}).get(str(r["pk"])) or {}
        if gs.get("frozen") or float(gs.get("backoff_until") or 0) > t:
            continue
        if r.get("state") in ("live", "delayed"):
            out.append({"pk": r["pk"], "calls": ["wp"], "why": "live"})
        elif r.get("state") == "final" and not gs.get("final_built"):
            out.append({"pk": r["pk"], "calls": ["wp", "box", "feed", "content"], "why": "final"})
    return out


def selfcheck(paths: dict | None = None) -> int:
    paths = paths or resolve_paths()
    hb = read_heartbeat(paths)
    print(f"scores job   : {Path(__file__).resolve()}")
    print(f"store        : {paths['store']}")
    print(f"out          : {paths['out']} (SCORES_LIVE={sc.SCORES_LIVE})")
    print(f"heartbeat    : {paths['heartbeat']}")
    if not hb:
        print("scheduler    : NEVER RUN on this machine. Nothing has executed this job here, so no cron line or "
              "scheduled task is reaching it.")
        print("               Box: install deploy/scores-crontab.example. Windows: deploy\\scores-task.ps1 -Register.")
        return 1
    print(f"scheduler    : last ran {hb.get('last_run_utc')} UTC")
    print(f"last action  : {hb.get('action')} ({hb.get('state')}): {hb.get('reason')}")
    if hb.get("action") in LOUD_ACTIONS or hb.get("exit") not in (0, None):
        print("state        : BAD. The last invocation failed; read logs/scores-job.log.")
        return 1
    return 0


def _setup_logging(log_file: str | None, verbose: bool) -> None:
    handlers: list = [logging.StreamHandler(sys.stdout)]
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.handlers.RotatingFileHandler(p, maxBytes=5 * 1024 * 1024, backupCount=2,
                                                         encoding="utf-8")]
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", handlers=handlers, force=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MLB Scores job (SCORES_2). Cron it every 2 minutes; it decides.")
    ap.add_argument("--why", action="store_true", help="print the gate's opinion; no call, no write")
    ap.add_argument("--selfcheck", action="store_true", help="has the scheduler reached this job here")
    ap.add_argument("--dry-run", action="store_true", help="what this tick would fetch; no call, no write")
    ap.add_argument("--date", help="rebuild one official date (YYYY-MM-DD) now")
    ap.add_argument("--backfill", help="A:B, two past official dates, never before HISTORY_FLOOR")
    ap.add_argument("--log-file", help="log to this file (3 x 5 MB rotating) instead of stdout")
    ap.add_argument("--no-jitter", action="store_true", help="skip the 0 to 20 s start jitter")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    start = time.time()
    _setup_logging(args.log_file, args.verbose)
    emit = log.warning if args.log_file else print

    if args.selfcheck:
        return selfcheck()
    if args.why:
        paths = resolve_paths()
        why = bad_out(paths)
        if why:
            print(f"bad_out: {why}")
            return 2
        hold, hold_why = epoch_hold()
        if hold:
            print(f"epoch_hold: {hold_why}")
            return 0
        d = decide(_utcnow(), read_json(paths["slate"]), load_state(paths), tick=tick_of(start),
                   embed=embed_effective(paths["out"]))
        print(f"{d['action']}: {d['reason']}")
        print(f"  {'; '.join(f'{k}={v}' for k, v in d.items() if k != 'reason')}")
        print(f"  out={paths['out']} (SCORES_LIVE={sc.SCORES_LIVE}). --why reads this job's own slate and state only; "
              "it makes no call and writes nothing.")
        return 0
    try:
        if args.backfill:
            if not re.match(r"^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$", args.backfill):
                emit("FAIL: --backfill takes A:B as YYYY-MM-DD:YYYY-MM-DD")
                return 2
            paths = resolve_paths()
            why = bad_out(paths)
            if why:
                emit(f"FAIL: bad_out: {why}")
                return 2
            hold, hold_why = epoch_hold()
            if hold:
                emit(f"skip: epoch_hold: {hold_why}")
                return 0
            lock = JobLock(paths["lock"])
            if not lock.acquire():
                emit("skip: overlap: another invocation holds the job lock")
                return 0
            try:
                a, b = args.backfill.split(":")
                res = backfill(a, b, paths=paths, lock=lock)
            finally:
                lock.release()
            write_heartbeat(paths, res, _utcnow())
            append_runlog(paths, res, _utcnow())
        else:
            if args.date and (not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date) or args.date < HISTORY_FLOOR):
                emit(f"FAIL: --date takes one YYYY-MM-DD no earlier than HISTORY_FLOOR {HISTORY_FLOOR}")
                return 2
            res = run(start=start, jitter=not (args.no_jitter or args.dry_run or args.date), dry_run=args.dry_run,
                      only_date=args.date)
    except Exception:                                     # noqa: BLE001
        log.exception("scores_job: the invocation crashed")
        return 1
    if args.dry_run:
        print(f"{res['action']}: {res['reason']}")
        for p in res.get("plan") or []:
            print(f"  would fetch {p}")
        return 0
    acted = res.get("action") not in ("none", "backoff", "overlap", "epoch_hold")
    if acted or res.get("exit") or args.verbose:
        verdict = "FAIL" if res.get("exit") else "ok"
        emit(f"{verdict}: {res.get('action')}: {res.get('reason')}")
    return int(res.get("exit") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
