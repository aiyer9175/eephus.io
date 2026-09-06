"""Fire the CLOSE odds snapshot near the slate's first pitch. Self-gating.

WHY THIS EXISTS. Closing line value is the honest validation metric for the
betting record: a winning bet at bad CLV is variance, a losing bet at good CLV
was a correct decision. Grading it needs a second odds capture taken near first
pitch. betting_ingest deliberately installs no timer and says so ("the box owns
the scheduling"), because the right moment is DATA: first pitch moves by three
or four hours between a getaway day and a night slate, so any fixed cron time is
either too early (not a closing line) or too late (games already started).

THE SHAPE. Rather than compute a cron time each morning and install it, this job
is designed to be run OFTEN and act ONCE. Cron it every 15 minutes ALL DAY under
TZ=UTC; it exits quietly on every invocation except the one inside the firing
window. That makes it robust to doubleheaders, rain delays, schedule changes and
a box that was asleep, none of which a fixed cron survives.

AND THE CRON WINDOW IS THE PRIME SUSPECT FOR ZERO CAPTURES (2026-08-09 owner
decision, binding). deploy/betting-crontab.example shipped `*/15 12-23 * * *` in
BOX-LOCAL time. The box timezone is undocumented, and if the box is UTC that
window is 08:00 to 19:00 ET: it closes before a 7:05pm ET first pitch on most of
the calendar and misses every late slate outright. Measured on 2026-08-09, the
odds cache holds 4 open snapshots and ZERO close snapshots, so CLV has never
been gradeable for any slate. The entry is now `*/15 * * * *` with `TZ=UTC`, and
every window decision is made HERE, in `decide`, against UTC instants. That is
correct under any box timezone, which is the only property worth having when
nobody can say what the box timezone is.

THE WINDOW HAS TWO ANCHORS, NOT ONE. The firing TARGET is read off the games
that can still be bet, so a postponed early game cannot drag the capture hours
forward. The refusal BOUNDARY is read off a wider list that also holds the games
already under way, because those are the ones a snapshot taken now would price
IN GAME. Reading both off the bettable list (which is what shipped on
2026-08-05) let the job fire after a first pitch that had already happened, and
an in-game price stamped "close" grades as CLV forever.

WHAT IT COSTS. Nothing until it fires, then one snapshot (3 credits on the
free tier's 500/month with the shipped market set). It refuses to fire twice for
the same slate date, so a misconfigured cron cannot drain the quota: the guard
is a real lookup of today's close snapshot, not a lockfile.

EXIT CODES: 0 whenever the job behaved correctly, INCLUDING every no-op. A
scheduler should not page anybody because it is 2pm and first pitch is at 7.
Non-zero only for a genuine failure, of which there are exactly two here and
both are new (2026-08-05):

  * A STALE SLATE. `decide` read the slate date and never compared it to the
    day it was running. One skipped nightly build leaves data/fantasy.json
    holding a past slate, whose first pitch is long gone, so every one of the
    ~48 cron fires that day took the "too late: first pitch has passed" branch
    and exited 0. The job looked healthy while the close capture silently
    stopped happening, and CLV is not recoverable after the fact: the only
    honest reading of a slate dated before today is that the pipeline broke.
  * AN UNREADABLE CLOSE SNAPSHOT. The once-per-slate guard was
    `if bi.closing_snapshot(day)`, whose loader returns None for a file that
    exists but will not parse. That FAILS OPEN: a truncated snapshot made the
    guard read "no snapshot yet" and the job re-fired every 15 minutes for the
    rest of the evening, which is the failure mode the whole self-gating shape
    was built to make impossible.

    python tools/betting_close_job.py            # the cron entry point
    python tools/betting_close_job.py --dry-run  # decide and report, spend nothing
    python tools/betting_close_job.py --why      # explain today's window and exit
"""
from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("betting_close_job")

#: PROOF OF LIFE, and it answers the one question the RED could not.
#:
#: snapshot_health measures close capture off .cache/odds/ and reports zero
#: captures as "the close cron is either not installed or is running in the
#: wrong timezone window". Those are different repairs and the artifact could
#: not tell them apart, because a job that runs 96 times a day and correctly
#: no-ops 95 of them leaves no trace at all until the night it fires. So every
#: invocation stamps this file, including the refusals.
#:
#: UNDER .cache/ ON PURPOSE, exactly like the odds snapshots it reports on.
#: data/job_heartbeat.json is git-tracked and deploy/nightly-build.sh runs
#: `git checkout -- .` before the build, so a heartbeat written by the 19:00
#: close job is reverted before the 03:10 pipeline could read it. That is not a
#: hypothetical: it is why snapshot_health measures the cache in the first place.
HEARTBEAT_PATH = ROOT / ".cache" / "betting" / "close_job_heartbeat.json"


def write_heartbeat(d: dict, *, path: Path | None = None) -> None:
    """Record that the job RAN, whatever it decided.

    Best effort and silent on failure: telemetry must never be the reason a
    close capture does not happen."""
    p = path or HEARTBEAT_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_run_utc": datetime.now(timezone.utc)
                            .replace(microsecond=0).isoformat(),
            "slate_date": d.get("slate_date"),
            "fired": bool(d.get("fire")),
            "error": bool(d.get("error")),
            "reason": d.get("reason"),
            "target_first_pitch": d.get("target_first_pitch"),
            "fire_at": d.get("fire_at"),
            "games": d.get("games"),
        }
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        log.warning("betting_close_job: could not write the heartbeat; the "
                    "capture is unaffected", exc_info=True)


def read_heartbeat(path: Path | None = None) -> dict | None:
    """The last recorded invocation, or None when the job has never run here."""
    p = path or HEARTBEAT_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


#: The persisted result of the last calibration close-attach. Under .cache/
#: for the same reason the heartbeat is: deploy/nightly-build.sh runs
#: `git checkout -- .` before the build, so a tracked stamp would be reverted
#: before anything could read it.
#:
#: WHY IT IS PERSISTED AT ALL. data/betting_learning.json explains an empty
#: market-move block, and until 2026-08-16 it explained it by guessing: it
#: asserted a book mismatch that no run had ever measured. This file is what
#: lets it cite what the attach actually did, n_book_mismatch included, and
#: claim nothing beyond it.
ATTACH_RESULT_PATH = ROOT / ".cache" / "betting" / "close_attach_result.json"


def write_attach_result(res: dict, *, path: Path | None = None) -> None:
    """Best effort and silent on failure, same posture as the heartbeat:
    telemetry must never be the reason a ledger write does not land."""
    p = path or ATTACH_RESULT_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(res)
        payload["written_at"] = (datetime.now(timezone.utc)
                                 .replace(microsecond=0).isoformat())
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        log.warning("betting_close_job: could not persist the attach result; "
                    "the ledger write is unaffected", exc_info=True)


def attach_closes(day: str | None, *, ledger_path: Path | None = None,
                  result_path: Path | None = None) -> dict:
    """Attach this slate's closing prices to the calibration ledger's rows
    that are still waiting for one, and persist what happened.

    THE SELECTOR READS THE FOLDED ROW, NOT A PHASE TAG. As shipped, this
    caller filtered bc.rows() on r["phase"] == PHASE_OPEN. But rows() is the
    FOLDED view, one row per priced side with every phase merged, and it
    deliberately drops `phase` while folding, so the filter matched nothing:
    `opens` was always empty, close_events_for_calibration was handed an empty
    list, and the first night the cron ever fired would have attached zero
    closes while printing a healthy-looking zero. The defect was in the tree
    from the day the caller shipped (2026-08-09) and could never have worked;
    it went unnoticed for the same reason the whole chain sat idle, the cron
    was never installed, so no production run ever reached the line. Found by
    reading the fold, 2026-08-16. A row still awaiting its close is one for
    this slate with no close_odds and no result, and those are field names the
    folded row actually carries."""
    import betting_export as be
    import tools.betting_calibration as bc

    if not day:
        res = {"closed": 0, "n_no_close": 0, "n_book_mismatch": 0,
               "n_open_rows": 0, "slate_date": None,
               "reason": "no slate date to attach against"}
        write_attach_result(res, path=result_path)
        return res
    opens = [r for r in bc.rows(path=ledger_path)
             if r.get("slate_date") == day
             and r.get("close_odds") is None
             and not r.get("result")]
    ev = be.close_events_for_calibration(day, opens)
    res = bc.append_close(ev, path=ledger_path)
    res["slate_date"] = day
    res["n_open_rows"] = len(opens)
    write_attach_result(res, path=result_path)
    return res

# Fire this many minutes BEFORE the earliest first pitch. Far enough out that
# the request completes while the market is still open, close enough that the
# line is genuinely a closing line. The Odds API updates on the order of a
# minute, so a tighter window buys nothing and risks missing the capture.
LEAD_MINUTES = 10

# How long after the target the job may still fire. Covers a box that was
# asleep, a cron that ran late, or a slow previous invocation. Past first pitch
# the number stops being a closing line, so the window closes hard there.
#
# THE TARGET AND THE BOUNDARY ARE READ OFF DIFFERENT SLATES, and that is the
# whole of the fix below. See `_window_games`.
GRACE_MINUTES = 8

# Hours to shift a UTC instant back by to get the SLATE DATE it belongs to.
# A slate dated D runs from roughly 17:00Z on D to 06:00Z on D+1, so the UTC
# date is simply the wrong anchor after about 8pm Pacific: a west-coast game
# that starts at 02:10Z is on the previous day's slate and the guard below must
# not call that slate stale. Shifting back 8 hours (US Pacific standard, the
# westernmost MLB market) puts every first pitch and every extra inning on its
# own slate date. It is deliberately not a timezone lookup: this needs to be
# right to the day, not to the minute, and a tz database on the build box is one
# more thing that can be missing at 6am.
SLATE_DAY_OFFSET_HOURS = 8

# THE OTHER OFFSET, AND WHY THERE ARE TWO (2026-08-09).
#
# betting_ingest.slate_date_of shifts back 4 hours (US Eastern, which is what
# MLB's officialDate follows) to answer "which slate does this FIRST PITCH
# belong to". This file shifts back 8 (US Pacific) to answer "which slate could
# still be live RIGHT NOW". Those are different questions and the two answers
# legitimately differ for the four hours between 04:00Z and 08:00Z: at 2am ET a
# west-coast game from yesterday's card may still be in extra innings, so
# "which slate is live" is yesterday while "which date is it" is today.
#
# Reconciled by USING EACH ONE WHERE IT FAILS SAFE, rather than by picking one
# and being wrong for four hours a night:
#   * the STALE-SLATE guard (a slate too old to close) compares against the
#     WESTERNMOST day, so a slate that could still be live is never called dead;
#   * the FUTURE-SLATE skip (a slate not started yet) compares against the
#     EASTERNMOST day, so a slate that has already begun somewhere is never
#     called tomorrow.
# Both guards therefore err toward staying awake, which costs one log line, and
# never toward skipping a capture, which costs a slate's CLV permanently.
SLATE_DAY_OFFSET_HOURS_EAST = 4


def _parse_stamp(s: str) -> datetime | None:
    """The schedule block's ISO stamp, normalized to aware UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def slate_day(now: datetime) -> str:
    """The WESTERNMOST slate date a UTC instant can still belong to, which is
    the one the stale-slate guard compares against. See
    SLATE_DAY_OFFSET_HOURS."""
    return (now - timedelta(hours=SLATE_DAY_OFFSET_HOURS)).date().isoformat()


def slate_day_east(now: datetime) -> str:
    """The EASTERNMOST slate date a UTC instant can belong to: the same anchor
    betting_ingest.slate_date_of uses to stamp a capture. The future-slate skip
    compares against this one. See SLATE_DAY_OFFSET_HOURS_EAST."""
    return (now - timedelta(hours=SLATE_DAY_OFFSET_HOURS_EAST)).date().isoformat()


def close_snapshot_state(day: str) -> tuple[str, str]:
    """(state, detail) for the once-per-slate guard, where state is one of
    "captured", "none" or "unreadable".

    THE GUARD USED TO FAIL OPEN. `bi.closing_snapshot(day)` walks the cache and
    calls `load_snapshot`, which returns None both for "there is no file" and for
    "the file is there and will not parse". Those are opposite answers: the first
    means fire, the second means a capture already happened (or was attempted)
    and firing again buys nothing while spending credits every 15 minutes until
    midnight. So the unreadable case is detected here, from the filenames, and
    the job refuses rather than guessing.

    A close snapshot that reads back cleanly is the ONLY thing that counts as
    captured; anything unreadable for the date is treated as a hard stop, because
    an unparseable file in the odds cache is a real failure whichever kind it
    turned out to be.

    AND THE TWO HALVES ASKED DIFFERENT QUESTIONS (2026-08-09). The "captured"
    half matches on the wrapper's `slate_date`, which betting_ingest computes in
    US Eastern precisely because a capture can land under the neighbouring UTC
    date. The "unreadable" half matched on `m["date"]`, the FILENAME date, which
    is UTC. So a close capture that was truncated while being written past UTC
    midnight - the 10:10pm ET first pitch, which is exactly when this job fires
    on a late West Coast slate - landed under tomorrow's filename, the scan for
    that day found nothing, and the fail-closed guard failed OPEN: the job
    re-fired every fifteen minutes against a 500-credit monthly budget. Widened
    by one day on each side, the same window `latest_snapshot` already uses."""
    import betting_ingest as bi

    if bi.closing_snapshot(day):
        return "captured", f"close snapshot already exists for {day}; a slate gets one"
    bad = [m["path"].name for m in bi.list_snapshots()
           if abs(bi._day_delta(m["date"], day)) <= 1 and bi.load_snapshot(m["path"]) is None]
    if bad:
        return "unreadable", (f"{len(bad)} odds snapshot file(s) for {day} exist but will "
                              f"not parse ({', '.join(sorted(bad)[:3])}); refusing to fire "
                              f"because an unreadable file is not evidence that no close "
                              f"was captured, and re-firing every 15 minutes would drain "
                              f"the monthly quota")
    return "none", ""


def _window_games(day: str, bettable: list[dict]) -> list[dict]:
    """The slate whose earliest first pitch is the REFUSAL BOUNDARY, which is
    NOT the slate that picks the firing target.

    The target is chosen off the bettable games because a postponed 1:05 game
    used to pull the whole card's capture six hours early. Reading the boundary
    off that same list (2026-08-05) was a regression: a game that flips to Live
    leaves the bettable slate, the earliest first pitch jumps forward past it,
    and the job may then fire at or after a first pitch that has already
    happened. `betting_export.anchors_close_window` carries the measurement and
    the reasoning; here it is applied to the FULL slate for the target date, so
    a game already under way is back in the boundary and a Final or postponed
    one stays out of it.

    The date is passed explicitly rather than left to `slate_games` to pick,
    because an unfiltered read chooses the earliest date ON FILE and yesterday's
    finished games are still in the schedule block. That would silently move the
    boundary to a slate this job is not capturing.

    BOTH CAPABILITIES ARE CHECKED, NOT ASSUMED. `be.slate_games` is a seam that
    gets replaced (the close-job tests install a two-game double; a diagnosis can
    install a fixture), and this runs inside a cron whose one job is to never
    crash. A betting_export that predates either piece degrades to the bettable
    slate, which is exactly the pre-fix behaviour, instead of raising TypeError
    or AttributeError every fifteen minutes."""
    import betting_export as be

    anchors = getattr(be, "anchors_close_window", None)
    try:
        widened = "include_unbettable" in inspect.signature(be.slate_games).parameters
    except (TypeError, ValueError):
        widened = False
    if anchors is None or not widened:
        log.info("betting_close_job: betting_export cannot widen the slate; the refusal "
                 "boundary falls back to the bettable games")
        return bettable
    wide = [g for g in (be.slate_games(day, include_unbettable=True) or []) if anchors(g)]
    # `wide` is a superset of `bettable` by construction. An empty one means the
    # two reads disagreed about the date, so keep the list known to be real.
    return wide or bettable


def decide(now: datetime | None = None) -> dict:
    """Should the close snapshot fire right now? Pure: reads artifacts, spends
    nothing, writes nothing. Returns the decision and the reasoning behind it so
    a dry run and the real run cannot disagree."""
    import betting_export as be
    import betting_ingest as bi

    now = now or datetime.now(timezone.utc)
    out: dict = {"now": now.replace(microsecond=0).isoformat(), "fire": False}

    if not bi.configured():
        out["reason"] = f"no {bi.ENV_KEY} in the environment; nothing to pull"
        return out

    # THE TARGET SLATE. `be.slate_games` drops Final, postponed and in-progress
    # rows. That filter is load-bearing HERE, not just on the board: the target
    # below is anchored on min(datetime) over the slate, so one postponed 1:05
    # game used to pull the close capture six hours early for every other game
    # on the card. The re-filter is belt and braces for a caller that ever hands
    # us a raw list. It decides WHEN TO FIRE and nothing else: the boundary that
    # decides WHEN IT IS TOO LATE comes off the wider slate in `_window_games`,
    # because this list also drops the games that have already started, which
    # are precisely the ones a close capture must never be taken after.
    games = [g for g in (be.slate_games() or []) if be.is_bettable(g)]
    if not games:
        out["reason"] = "no games on the slate (off day, or fantasy.json has no schedule block)"
        return out
    out["games"] = len(games)

    stamp = bi.closing_window(games)
    target_first = _parse_stamp(stamp)
    if target_first is None:
        out["reason"] = "slate carries no usable first-pitch stamp"
        return out
    out["target_first_pitch"] = target_first.replace(microsecond=0).isoformat()

    day = min(g.get("date") or "" for g in games if g.get("date"))
    out["slate_date"] = day
    # TWO ANCHORS, EACH USED WHERE IT FAILS SAFE. See SLATE_DAY_OFFSET_HOURS_EAST.
    today = slate_day(now)
    today_east = slate_day_east(now)
    out["today"] = today
    out["today_east"] = today_east
    if day < today:
        # THE STALE-SLATE GUARD. Without it a past slate reads as a slate whose
        # first pitch has passed, and the job exits 0 all day while the close
        # capture quietly never happens. Non-zero, because there is nothing this
        # job can do about it and somebody has to rebuild the schedule before
        # tonight's lines close.
        out["error"] = True
        out["reason"] = (f"STALE SLATE: data/fantasy.json's earliest bettable slate is "
                         f"{day} but today is {today}. The schedule refresh has not run, "
                         f"so there is no closing line to capture and every fire today "
                         f"would look like a normal 'first pitch has passed' no-op")
        return out
    if day > today_east:
        # Compared against the EASTERNMOST day on purpose. Against the western
        # one this branch fired for the four hours between 04:00Z and 08:00Z on
        # every slate, reporting "nothing left to close tonight" at 2am ET about
        # a slate that starts in fifteen hours - harmless under the old
        # afternoon-only cron and a real skip under the all-day one.
        out["reason"] = (f"the next bettable slate is {day} and today is {today_east}; "
                         f"nothing left to close tonight")
        return out

    snap_state, snap_detail = close_snapshot_state(day)
    if snap_state == "captured":
        out["reason"] = snap_detail
        return out
    if snap_state == "unreadable":
        out["error"] = True
        out["reason"] = snap_detail
        return out

    # THE REFUSAL BOUNDARY, off the wider slate: the earliest first pitch among
    # the games that can still be bet PLUS the games already being played. It is
    # always at or before `target_first`, and the gap between them is exactly the
    # in-game window this job must not fire inside.
    window = _window_games(day, games)
    out["window_games"] = len(window)
    boundary = _parse_stamp(bi.closing_window(window)) or target_first
    out["first_pitch"] = boundary.replace(microsecond=0).isoformat()

    target = target_first - timedelta(minutes=LEAD_MINUTES)
    out["fire_at"] = target.replace(microsecond=0).isoformat()
    # THE BOUNDARY IS TESTED BEFORE THE TARGET. Once a first pitch has passed the
    # answer is "too late" whatever the target says, and on a slate with a game
    # already under way the target is still in the future: checking "too early"
    # first would report a window about to open on a capture that may never be
    # taken.
    if now >= boundary:
        # Named, because "too late" on a slate whose next bettable game has not
        # started yet reads like a bug until you know a game already has.
        started = ("" if boundary >= target_first else
                   f" A game on this slate started at {out['first_pitch']}, ahead of the "
                   f"{out['target_first_pitch']} game the window targets, so any capture "
                   f"now would carry an in-game price for it.")
        out["reason"] = ("too late: first pitch has passed, so this would not be a "
                         "closing line. Skipping rather than recording a bad one." + started)
        return out
    if now < target:
        mins = int((target - now).total_seconds() // 60)
        out["reason"] = f"too early: {mins} min until the window opens"
        return out
    if now > target + timedelta(minutes=GRACE_MINUTES):
        # Inside the window but past the grace period: still before first pitch,
        # so the line is still closing-ish. Fire, and say it was late.
        out["late"] = True

    out["fire"] = True
    out["reason"] = "inside the closing window"
    out["credits"] = bi.credits_for()
    return out


def _book_close_credits(cost: int, note: str) -> None:
    """Charge the shared tier ledger for a close capture. Never raises.

    Booked on both the success and the failure path: The Odds API bills on the
    request, so a call that reached the provider and then raised has already
    cost its credits."""
    try:
        import betting_credits as _bc
        _bc.record("close", int(cost), note=str(note))
    except Exception:                                     # noqa: BLE001
        log.warning("betting_close_job: could not book %s close credits",
                    cost, exc_info=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and report; never spends a credit")
    ap.add_argument("--why", action="store_true",
                    help="explain today's window and exit (same as --dry-run)")
    ap.add_argument("--selfcheck", action="store_true",
                    help="print the install state: whether this machine has "
                         "ever run the job, when, and what it last decided")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.selfcheck:
        # THE POST-INSTALL CHECK. `--why` answers "what would it do now", which
        # a human can read on a machine where nothing is scheduled and mistake
        # for a working install. This answers the different question: has the
        # SCHEDULER ever reached this job on this machine.
        hb = read_heartbeat()
        import betting_ingest as _bi
        print(f"close job     : {Path(__file__).resolve()}")
        print(f"odds cache    : {_bi.CACHE_DIR}")
        print(f"api key set   : {_bi.configured()}")
        print(f"heartbeat     : {HEARTBEAT_PATH}")
        if not hb:
            print("scheduler     : NEVER RUN on this machine. Nothing has "
                  "executed this job here, so no cron or task is reaching it.")
            print("               Linux: install deploy/betting-crontab.example "
                  "with `crontab -e`.")
            print("               Windows: deploy/betting-close-task.ps1 -Register")
            return 1
        print(f"scheduler     : last ran {hb.get('last_run_utc')} UTC")
        print(f"last decision : {hb.get('reason')}")
        print(f"last slate    : {hb.get('slate_date')}  fired={hb.get('fired')}")
        return 0

    try:
        d = decide()
    except Exception:
        log.exception("betting_close_job: could not decide")
        return 1

    line = "; ".join(f"{k}={v}" for k, v in d.items() if k != "reason")
    verdict = "FIRE" if d["fire"] else ("FAIL" if d.get("error") else "skip")
    print(f"{verdict}: {d['reason']}")
    if args.verbose or args.dry_run or args.why:
        print(f"  {line}")

    if args.dry_run or args.why:
        # No heartbeat on an inspection run. --why is documented as spending
        # nothing, and a heartbeat written by a human at a terminal would report
        # the CRON as alive on a box where it is not installed, which is the
        # precise question the heartbeat exists to answer.
        return 0

    # Stamped before the capture, so a run that dies inside betting_ingest still
    # proves the scheduler reached the job.
    write_heartbeat(d)

    if d.get("error"):
        # The two states a scheduler MUST hear about: a slate that is not today
        # (nothing will be captured and nobody would notice) and an unreadable
        # snapshot for today (the once-per-slate guard cannot be trusted). Every
        # other no-op stays exit 0 on purpose.
        log.error("betting_close_job: %s", d["reason"])
        return 2
    if not d["fire"]:
        return 0

    # THE TIER GUARD. The close job's own window logic decides WHETHER this is
    # the right moment; this decides whether the month can afford it. Four jobs
    # share one 500-credit tier and until 2026-09-06 none of them could see the
    # others, so whichever ran first could exhaust it and every later job would
    # simply get provider errors on a budget the code believed was fine.
    #
    # The refusal is exit 0, not an error. A month that has spent its close
    # allocation is a budget state, not a broken job, and returning non-zero
    # would page somebody every fifteen minutes for the rest of the month.
    try:
        import betting_ingest as bi
    except Exception:
        log.exception("betting_close_job: cannot import betting_ingest")
        return 1
    _cost = 3
    try:
        import betting_credits as _bc
        _cost = int(bi.credits_for())
        _okc, _whyc = _bc.check("close", _cost)
    except Exception:                                     # noqa: BLE001
        _okc, _whyc = True, "credit ledger unavailable; proceeding unguarded"
        log.warning("betting_close_job: credit ledger unusable", exc_info=True)
    if not _okc:
        log.warning("betting_close_job: %s", _whyc)
        print(f"  no capture: {_whyc}")
        return 0
    log.info("betting_close_job: credits %s", _whyc)

    try:
        status = bi.run("close")
    except Exception:
        # Sent but failed still bills.
        _book_close_credits(_cost, "raised")
        log.exception("betting_close_job: close snapshot failed")
        return 1
    _book_close_credits(_cost, str((status or {}).get("last_run"))[:80])
    print(f"  {status.get('last_run')}")

    # Grade the record against the close we just captured. This is the ONLY
    # moment the closing line for this slate is guaranteed to be on disk, and
    # CLV is unrecoverable after the fact, so it runs here rather than on the
    # nightly. It writes a SIDECAR: the published record is append-only and a
    # closing price that lands hours after a pick is posted can never be written
    # back into the row it belongs to.
    #
    # Best effort on purpose. A grading failure must not make the close job
    # report a failed CAPTURE, because the capture is the irreplaceable half and
    # the grade can be rebuilt from it at any time.
    try:
        import betting_export as be
        clv = be.grade_record_clv()
        print(f"  clv: {clv['n_graded']} graded, {clv['n_ungraded']} ungraded")
        if clv["n_ungraded"]:
            log.warning("betting_close_job: %d pick(s) ungraded: %s",
                        clv["n_ungraded"], clv["ungraded_reasons"])
    except Exception:
        log.exception("betting_close_job: CLV grading failed; the close snapshot "
                      "IS captured and the grade can be rebuilt from it")

    # Attach the closing price to the CALIBRATION ledger's rows for this
    # slate. This is the other half of the close capture and it had no
    # production caller at all: append_close was reachable only from two tests,
    # so no `phase: close` row was ever written, market_move_pct was permanently
    # null, and data/betting_learning.json published a blocked_by describing a
    # repair that would not have repaired it. The selection itself was ALSO
    # broken as shipped, in a way that made the caller a guaranteed no-op; the
    # defect and its fix live in `attach_closes` above.
    #
    # Same posture as the CLV grade above: best effort, because the CAPTURE is
    # the irreplaceable half and every derived number can be rebuilt from it.
    try:
        res = attach_closes(d.get("slate_date"))
        print(f"  calibration: {res.get('closed', 0)} closing price(s) attached "
              f"({res.get('n_no_close', 0)} without a close, "
              f"{res.get('n_book_mismatch', 0)} book mismatch)")
    except Exception:
        log.exception("betting_close_job: attaching closing prices to the "
                      "calibration ledger failed; the close snapshot IS "
                      "captured and this can be rebuilt from it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
