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

WHAT IT COSTS. Nothing until it fires, then one snapshot (3 credits on the
free tier's 500/month with the shipped market set). It refuses to fire twice for
the same slate date, so a misconfigured cron cannot drain the quota: the guard
is a real lookup of today's close snapshot, not a lockfile.

EXIT CODES: 0 whenever the job behaved correctly, INCLUDING every no-op. A
scheduler should not page anybody because it is 2pm and first pitch is at 7.
Non-zero only for a genuine failure.

    python tools/betting_close_job.py            # the cron entry point
    python tools/betting_close_job.py --dry-run  # decide and report, spend nothing
    python tools/betting_close_job.py --why      # explain today's window and exit
"""
from __future__ import annotations

import argparse
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
GRACE_MINUTES = 8


def _parse_stamp(s: str) -> datetime | None:
    """The schedule block's ISO stamp, normalized to aware UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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

    games = be.slate_games()
    if not games:
        out["reason"] = "no games on the slate (off day, or fantasy.json has no schedule block)"
        return out
    out["games"] = len(games)

    stamp = bi.closing_window(games)
    first = _parse_stamp(stamp)
    if first is None:
        out["reason"] = "slate carries no usable first-pitch stamp"
        return out
    out["first_pitch"] = first.replace(microsecond=0).isoformat()

    day = min(g.get("date") or "" for g in games if g.get("date"))
    out["slate_date"] = day
    if bi.closing_snapshot(day):
        out["reason"] = f"close snapshot already exists for {day}; a slate gets one"
        return out

    target = first - timedelta(minutes=LEAD_MINUTES)
    out["fire_at"] = target.replace(microsecond=0).isoformat()
    if now < target:
        mins = int((target - now).total_seconds() // 60)
        out["reason"] = f"too early: {mins} min until the window opens"
        return out
    if now >= first:
        out["reason"] = ("too late: first pitch has passed, so this would not be a "
                         "closing line. Skipping rather than recording a bad one")
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
    print(f"{'FIRE' if d['fire'] else 'skip'}: {d['reason']}")
    if args.verbose or args.dry_run or args.why:
        print(f"  {line}")

    if args.dry_run or args.why or not d["fire"]:
        return 0

    try:
        import betting_ingest as bi
        status = bi.run("close")
    except Exception:
        log.exception("betting_close_job: close snapshot failed")
        return 1
    print(f"  {status.get('last_run')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
