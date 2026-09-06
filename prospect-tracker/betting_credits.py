"""ONE credit ledger for every job that spends against The Odds API.

WHY THIS EXISTS. Four jobs now bill the same 500-credit monthly free tier, and
until today not one of them could see the others:

    open capture     3/day    ~93/month   run_monthly.py --odds-open
    close capture    3/day    ~93/month   tools/betting_close_job.py
    props pull       4/event  up to 120   betting_export props path
    futures capture  ~5/week   ~20/month  (weekly outright capture, planned)

That totals about 326 of 500 when everything is armed. The arithmetic works, and
that is exactly what makes it dangerous: nothing enforces it. The props guard in
betting_ingest counts props alone against its own cap, and the two snapshot jobs
count nothing at all. Whichever job runs first in a month can spend the tier and
every later job simply gets errors from the provider, on a budget the code
believed was fine.

THE PROVIDER'S METER IS THE AUTHORITY, NOT THIS LEDGER. Our count can only ever
be a lower bound on real spend: a manual call, a second box, a retried request or
a run before this module existed all bill without passing through here. So every
check takes the MINIMUM of our own headroom and the provider's reported
`remaining`, read off the newest cached response. When the two disagree the
provider wins, and the disagreement is reported rather than smoothed over,
because a ledger quietly drifting below the truth is worse than no ledger.

WHAT A REFUSAL MEANS. It is a refusal BEFORE the request. This is the only place
it can be, because betting_ingest.run() fetches before it writes: by the time any
error can be raised downstream the credits are already gone from the provider's
meter. A guard that fires after the call is not a guard.

Every refusal carries its arithmetic. A guard that only says no cannot be
audited, and the one thing worse than a job that overspends is a job that refuses
to run and nobody can tell why.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
LEDGER_DIR = ROOT / ".cache" / "betting"
ODDS_CACHE_DIR = ROOT / ".cache" / "odds"

#: The Odds API free tier. Not read from the provider: it is the plan we are on,
#: and if it ever changes this constant is the one place to change it.
TIER_MONTHLY = 500

#: Env override for a paid tier, so a box on a larger plan does not have to be
#: patched. Ignored when unparseable, because a typo must not silently raise the
#: budget.
ENV_TIER = "EEPHUS_ODDS_TIER_CREDITS"

#: PER-JOB ALLOCATIONS, and they deliberately do not sum to the tier.
#:
#: 100 + 100 + 120 + 30 = 350, leaving 150 unallocated. That reserve is not
#: slack to be reclaimed later; it is what absorbs the spend this ledger cannot
#: see (a manual pull, a second box, a retry that billed before it failed). The
#: allocations are also each slightly above the job's expected monthly draw
#: (93, 93, 120, 20) so that a 31-day month with one retry does not trip a
#: refusal on a job that is behaving correctly.
ALLOCATIONS: dict[str, int] = {
    "open": 100,
    "close": 100,
    "props": 120,
    "futures": 30,
}

JOBS = tuple(ALLOCATIONS)


def tier_monthly() -> int:
    raw = (os.environ.get(ENV_TIER) or "").strip()
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
            log.warning("%s is %r, which is not a positive credit count; "
                        "using the free-tier default %d", ENV_TIER, raw, TIER_MONTHLY)
        except ValueError:
            log.warning("%s is %r, which is not an integer; using the "
                        "free-tier default %d", ENV_TIER, raw, TIER_MONTHLY)
    return TIER_MONTHLY


def _month(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m")


def ledger_path(when: datetime | None = None) -> Path:
    """One file per calendar month, UTC.

    UTC and not box-local, because the provider's own meter resets on its
    calendar and a box in a western timezone would otherwise open a fresh
    ledger up to a day early and believe it had a full tier.
    """
    return LEDGER_DIR / f"credits-{_month(when)}.json"


def _empty(month: str) -> dict:
    return {"month": month, "total": 0,
            "by_job": {j: 0 for j in JOBS}, "history": []}


def load(path: Path | None = None, when: datetime | None = None) -> dict:
    p = Path(path) if path is not None else ledger_path(when)
    month = _month(when)
    if not p.exists():
        return _empty(month)
    try:
        led = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("credit ledger at %s is unreadable; treating the month as "
                    "UNKNOWN rather than empty", p)
        # An unreadable ledger must not read as "nothing spent yet". Report the
        # whole tier as consumed so the guard refuses until a human looks.
        bad = _empty(month)
        bad["total"] = tier_monthly()
        bad["unreadable"] = True
        return bad
    if led.get("month") != month:
        return _empty(month)
    led.setdefault("by_job", {})
    for j in JOBS:
        led["by_job"].setdefault(j, 0)
    led.setdefault("history", [])
    led.setdefault("total", sum(int(v or 0) for v in led["by_job"].values()))
    return led


def save(led: dict, path: Path | None = None,
         when: datetime | None = None) -> None:
    p = Path(path) if path is not None else ledger_path(when)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(led, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def provider_remaining(cache_dir: Path | None = None) -> tuple[int | None, str]:
    """(remaining, where it came from) off the newest cached odds response.

    Returns (None, reason) when nothing is cached, which is the normal state on
    a box that has never captured. A missing meter is NOT treated as zero: that
    would refuse the very first call of a month on every fresh checkout.
    """
    d = Path(cache_dir) if cache_dir is not None else ODDS_CACHE_DIR
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return None, "the odds cache directory could not be read"
    for f in reversed(files):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rem = ((obj or {}).get("credits") or {}).get("remaining")
        if rem is None:
            continue
        try:
            return int(rem), f.name
        except (TypeError, ValueError):
            continue
    return None, "no cached response carries a credits.remaining figure"


def check(job: str, cost: int, *, path: Path | None = None,
          when: datetime | None = None, ledger: dict | None = None,
          cache_dir: Path | None = None) -> tuple[bool, str]:
    """(ok, reason) BEFORE the request. Never raises.

    Three separate bars, and a request must clear all three:

      1. The job's own allocation, so one job cannot eat another's share.
      2. The tier total as this ledger counts it.
      3. The provider's reported remaining, which overrides both when it is
         lower, because it is the only figure that reflects spend we cannot see.
    """
    cost = int(cost)
    if job not in ALLOCATIONS:
        return False, (f"unknown job {job!r}; the ledger allocates to "
                       f"{sorted(ALLOCATIONS)} and refuses to spend against a "
                       "job it cannot account for")
    if cost <= 0:
        return True, "a zero-cost request spends nothing"

    led = ledger if ledger is not None else load(path, when)
    if led.get("unreadable"):
        return False, ("the credit ledger for this month is unreadable, so the "
                       "spend so far is unknown; refusing rather than guessing "
                       "it is zero. Delete or repair "
                       f"{ledger_path(when).name} to clear this.")
    tier = tier_monthly()
    spent_job = int(led["by_job"].get(job) or 0)
    spent_all = int(led.get("total") or 0)
    alloc = ALLOCATIONS[job]

    if spent_job + cost > alloc:
        return False, (f"refused BEFORE the request: {job} has spent "
                       f"{spent_job} of its {alloc} monthly credits and this "
                       f"call costs {cost}, which would breach its allocation. "
                       f"The tier has {tier - spent_all} left overall, so this "
                       "is a per-job limit and not an exhausted tier.")
    if spent_all + cost > tier:
        return False, (f"refused BEFORE the request: {spent_all} of {tier} "
                       f"monthly credits are spent across all jobs and this "
                       f"call costs {cost}, which would breach the tier.")

    rem, src = provider_remaining(cache_dir)
    if rem is not None and cost > rem:
        return False, (f"refused BEFORE the request: the provider's own meter "
                       f"reports {rem} credits remaining (from {src}) and this "
                       f"call costs {cost}. The provider is the authority on "
                       f"its own meter; this ledger counts {spent_all} spent, "
                       "which is a lower bound.")

    note = (f"{job}: {spent_job}+{cost} of {alloc}; tier {spent_all}+{cost} "
            f"of {tier}")
    if rem is not None:
        ours = tier - spent_all
        if rem < ours:
            note += (f"; the provider reports {rem} remaining against our {ours}, "
                     f"a {ours - rem}-credit gap this ledger cannot see")
        else:
            note += f"; provider reports {rem} remaining"
    return True, note


def record(job: str, cost: int, *, note: str = "", path: Path | None = None,
           when: datetime | None = None) -> dict:
    """Book actual spend. Call this AFTER the request, whether or not it
    succeeded: the provider bills on the request, not on the response, so a
    failed call that reached the API still cost its credits."""
    led = load(path, when)
    if led.get("unreadable"):
        led = _empty(_month(when))
    cost = int(cost)
    led["by_job"][job] = int(led["by_job"].get(job) or 0) + cost
    led["total"] = int(led.get("total") or 0) + cost
    led["history"].append({
        "at": (when or datetime.now(timezone.utc))
              .replace(microsecond=0).isoformat(),
        "job": job, "cost": cost, "note": str(note)[:200]})
    led["history"] = led["history"][-500:]
    save(led, path, when)
    return led


def status(*, path: Path | None = None, when: datetime | None = None,
           cache_dir: Path | None = None) -> dict:
    """The whole picture, for a log line or a selfcheck."""
    led = load(path, when)
    tier = tier_monthly()
    rem, src = provider_remaining(cache_dir)
    spent = int(led.get("total") or 0)
    by_job = {
        j: {"spent": int(led["by_job"].get(j) or 0),
            "allocation": ALLOCATIONS[j],
            "remaining": ALLOCATIONS[j] - int(led["by_job"].get(j) or 0)}
        for j in JOBS}
    out = {
        "month": led.get("month"),
        "tier": tier,
        "spent_all_jobs": spent,
        "remaining_by_this_ledger": tier - spent,
        "allocated": sum(ALLOCATIONS.values()),
        "unallocated_reserve": tier - sum(ALLOCATIONS.values()),
        "by_job": by_job,
        "provider_remaining": rem,
        "provider_source": src,
        "ledger_path": str(ledger_path(when)),
        "unreadable": bool(led.get("unreadable")),
    }
    if rem is not None:
        out["gap_provider_minus_ours"] = rem - (tier - spent)
        out["ledger_is_a_lower_bound"] = rem < (tier - spent)
    return out


def selfcheck() -> int:
    """Human-readable status. Exit 0 always: this reports, it does not gate."""
    import pprint
    pprint.pprint(status())
    return 0


if __name__ == "__main__":
    raise SystemExit(selfcheck())
