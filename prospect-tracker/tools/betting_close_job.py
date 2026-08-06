"""Fire the CLOSE odds snapshot near the slate's first pitch. Self-gating.

WHY THIS EXISTS. Closing line value is the honest validation metric for the
betting record: a winning bet at bad CLV is variance, a losing bet at good CLV
was a correct decision. Grading it needs a second odds capture taken near first
pitch. betting_ingest deliberately installs no timer and says so ("the box owns
the scheduling"), because the right moment is DATA: first pitch moves by three
or four hours between a getaway day and a night slate, so any fixed cron time is
either too early (not a closing line) or too late (games already started).

THE SHAPE. Rather than compute a cron time each morning and install it, this job
is designed to be run OFTEN and act ONCE. Cron it every 15 minutes across the
afternoon and evening; it exits quietly on every invocation except the one
inside the firing window. That makes it robust to doubleheaders, rain delays,
schedule changes and a box that was asleep, none of which a fixed cron survives.

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
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger("betting_close_job")

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
    """The slate date a UTC instant belongs to. See SLATE_DAY_OFFSET_HOURS."""
    return (now - timedelta(hours=SLATE_DAY_OFFSET_HOURS)).date().isoformat()


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
    turned out to be."""
    import betting_ingest as bi

    if bi.closing_snapshot(day):
        return "captured", f"close snapshot already exists for {day}; a slate gets one"
    bad = [m["path"].name for m in bi.list_snapshots()
           if m["date"] == day and bi.load_snapshot(m["path"]) is None]
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
    today = slate_day(now)
    out["today"] = today
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
    if day > today:
        out["reason"] = (f"the next bettable slate is {day} and today is {today}; nothing "
                         f"left to close tonight")
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and report; never spends a credit")
    ap.add_argument("--why", action="store_true",
                    help="explain today's window and exit (same as --dry-run)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

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
        return 0
    if d.get("error"):
        # The two states a scheduler MUST hear about: a slate that is not today
        # (nothing will be captured and nobody would notice) and an unreadable
        # snapshot for today (the once-per-slate guard cannot be trusted). Every
        # other no-op stays exit 0 on purpose.
        log.error("betting_close_job: %s", d["reason"])
        return 2
    if not d["fire"]:
        return 0

    try:
        import betting_ingest as bi
        status = bi.run("close")
    except Exception:
        log.exception("betting_close_job: close snapshot failed")
        return 1
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
