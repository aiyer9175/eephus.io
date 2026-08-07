# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""When did each scheduled job last ACTUALLY run?

THE CLASS THIS EXISTS FOR. Three separate jobs turned out to be configured and
inert on 2026-08-06, and every one of them looked healthy in its own artifact:

  * The betting odds snapshot. The API key was set, the provider was named,
    run_daily step 9e existed, and .cache/odds/ had never been created. Zero
    snapshots, for weeks. data/betting_status.json said `configured: true`.
  * The completed-games cache. It could never advance past the day it was first
    written, so the validation clock read as running and was not.
  * build_context and backtest. They ran only in main(), so the number they
    produce moved once a month at best while everything feeding it was nightly.

None of these raised. Each artifact was well-formed and internally consistent.
The missing fact was never "is this value wrong" but "did this job happen at
all", and nothing anywhere recorded that.

WHAT THIS RECORDS, and why each field earns its place:
  last_attempt_at   the job reached its own code. Distinguishes "the step never
                    executed" from "the step ran and failed", which are
                    different repairs.
  last_success_at   it finished its work. A job attempting nightly and failing
                    nightly is invisible if you only record attempts.
  last_result       a short human string, so a reader does not have to open a
                    log to learn what happened.
  n_attempts        cheap evidence of cadence. A counter stuck at 1 says the job
                    fired once ever, which is exactly the odds-snapshot shape.

WHAT IT DELIBERATELY DOES NOT DO. It does not decide whether a job is late. Only
the caller knows a job's cadence, and a threshold baked in here would be wrong
for half of them. `stale()` takes the expected interval as an argument and the
caller supplies it.

The file is small, committed, and written atomically through the shared
storage helper. It is meant to be READ BY A PERSON as well as by code, so it is
indented JSON with ISO timestamps rather than a compact blob.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("job_heartbeat")

ROOT = Path(__file__).parent
PATH = ROOT / "data" / "job_heartbeat.json"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def load(path: Path | None = None) -> dict:
    """The ledger, or an empty one. A missing file is a legitimate empty state:
    it means nothing has ever reported, which is itself the answer on a fresh
    box. A file that will not parse is logged and treated as empty rather than
    raising, because a broken heartbeat must never take down the job it is
    supposed to be observing."""
    p = Path(path or PATH)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("job_heartbeat: %s unreadable; treating as empty", p.name,
                    exc_info=True)
        return {}
    return d.get("jobs") or {} if isinstance(d, dict) else {}


def _write(jobs: dict, path: Path | None = None) -> None:
    p = Path(path or PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now().isoformat(),
        "what_this_is": ("when each scheduled job last actually ran. A job that "
                         "is configured but never fires looks healthy in its own "
                         "artifact; this is the file that would have caught it."),
        "jobs": dict(sorted(jobs.items())),
    }
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        try:
            from storage import _atomic_replace
        except Exception:                                     # noqa: BLE001
            _atomic_replace = None
        if _atomic_replace is not None:
            _atomic_replace(tmp, p)
        else:
            os.replace(tmp, p)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def record(job: str, *, ok: bool, result: str = "", path: Path | None = None) -> dict:
    """Record one run. Best effort: NEVER raises into the caller.

    A heartbeat that can break the job it observes is worse than no heartbeat,
    so every failure here is swallowed and logged. The caller wraps its real
    work; this must not add a new way for that work to fail."""
    try:
        jobs = load(path)
        row = jobs.get(job) or {}
        now = _now().isoformat()
        row["last_attempt_at"] = now
        row["n_attempts"] = int(row.get("n_attempts") or 0) + 1
        row["last_result"] = (result or ("ok" if ok else "failed"))[:200]
        if ok:
            row["last_success_at"] = now
            row["n_successes"] = int(row.get("n_successes") or 0) + 1
        jobs[job] = row
        _write(jobs, path)
        return row
    except Exception:                                         # noqa: BLE001
        log.warning("job_heartbeat: could not record %s", job, exc_info=True)
        return {}


def stale(job: str, *, max_age_hours: float, path: Path | None = None) -> dict:
    """Is this job overdue?

    Returns {"known": bool, "stale": bool, "age_hours": float|None, "why": str}.

    `known` is the field that matters most and the one a naive version would
    omit. A job that has NEVER reported is not the same as a job that ran and is
    now late: the first is usually a wiring bug and the second is usually an
    outage, and they get fixed in different places. Reporting both as "stale"
    would merge the two failures that this module exists to separate."""
    jobs = load(path)
    row = jobs.get(job)
    if not row:
        return {"known": False, "stale": True, "age_hours": None,
                "why": (f"{job} has never reported a run. Either the step does "
                        "not call record(), or it has never executed.")}
    last = row.get("last_success_at") or row.get("last_attempt_at")
    if not last:
        return {"known": False, "stale": True, "age_hours": None,
                "why": f"{job} has a row but no timestamp on it"}
    try:
        when = datetime.fromisoformat(last)
    except ValueError:
        return {"known": False, "stale": True, "age_hours": None,
                "why": f"{job} carries an unparseable timestamp {last!r}"}
    age = (_now() - when).total_seconds() / 3600.0
    over = age > max_age_hours
    never_ok = not row.get("last_success_at")
    return {
        "known": True,
        "stale": bool(over or never_ok),
        "age_hours": round(age, 2),
        "n_attempts": row.get("n_attempts"),
        "n_successes": row.get("n_successes", 0),
        "why": (f"{job} last succeeded {age:.1f}h ago against an expected "
                f"{max_age_hours:.0f}h" if over else
                f"{job} has attempted {row.get('n_attempts')} time(s) and never "
                "succeeded" if never_ok else
                f"{job} ran {age:.1f}h ago"),
    }


def report(expected: dict[str, float], path: Path | None = None) -> dict:
    """Roll up every job against its expected interval in hours.

    `expected` is supplied by the caller because cadence is the caller's
    knowledge, not this module's. Jobs present in the ledger but ABSENT from
    `expected` are reported separately rather than dropped: an unrecognised job
    is usually a rename, and silently ignoring it is how a heartbeat stops
    covering the thing it was added for."""
    jobs = load(path)
    out, bad = {}, []
    for job, hours in (expected or {}).items():
        s = stale(job, max_age_hours=hours, path=path)
        out[job] = s
        if s["stale"]:
            bad.append(s["why"])
    unexpected = sorted(set(jobs) - set(expected or {}))
    return {"jobs": out, "stale": bad, "n_stale": len(bad),
            "unrecognised_jobs": unexpected,
            "all_healthy": not bad and not unexpected}
