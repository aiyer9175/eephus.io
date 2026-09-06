"""The early-UTC open-odds capture, and the guard that keeps it from billing twice.

WHY THIS FILE EXISTS. `run_monthly.py --odds-open` is a NEW cron entry point that
makes a PAID external call (3 credits against a 500-credit monthly free tier). It
was added on 2026-09-06 because the nightly's hour was too late: 11 of the 22
cached snapshots landed after their own slate's first pitch, so more than half the
daily spend bought a price that was no longer an opening price.

Moving the call earlier is only safe because a guard stops the nightly's own step
9d-pre-odds from making a SECOND call for the same slate. That guard is the entire
safety property, and it cannot be delegated to the ingest layer:
betting_ingest.run() fetches BEFORE write_snapshot() can raise FileExistsError, so
the provider's meter is charged before a duplicate can be refused, and that error
only fires on an identical YYYY-MM-DD-HHMM filename anyway. Two calls a minute
apart both succeed and both bill.

So the refusal lives at the call site, in two places, and this file pins both. No
test here makes a network call; the ingest seam is replaced with a spy that FAILS
the test if it is reached on a path that should have skipped.

This module's history is the reason for the paranoia: the close job shipped with a
UTC-midnight slate bug that could fire a second paid snapshot for a slate already
captured, and separately shipped a six-hours-early window, and separately was
never installed on any box at all.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _slate_now() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d")


class _Spy:
    """Stands in for betting_ingest. Any call to run() is a billed call."""

    def __init__(self, *, armed=True, existing=None, raise_on_latest=False,
                 run_result=None):
        self._armed = armed
        self._existing = existing
        self._raise_on_latest = raise_on_latest
        self._run_result = run_result or {"last_run": "ok: captured 14 events"}
        self.run_calls = []
        self.latest_calls = []

    def configured(self):
        return self._armed

    def credits_for(self):
        return 3

    def latest_snapshot(self, kind=None, on_date=None):
        self.latest_calls.append((kind, on_date))
        if self._raise_on_latest:
            raise OSError("cache directory is unreadable")
        return self._existing

    def run(self, kind):
        self.run_calls.append(kind)
        return self._run_result


@pytest.fixture()
def rm():
    import run_monthly
    return run_monthly


class _Credits:
    """Stands in for betting_credits. Records what was checked and booked."""

    def __init__(self, *, allow=True, reason="ok"):
        self._allow = allow
        self._reason = reason
        self.checks = []
        self.records = []

    def check(self, job, cost, **kw):
        self.checks.append((job, cost))
        return self._allow, self._reason

    def record(self, job, cost, note="", **kw):
        self.records.append((job, cost, note))
        return {}


def _install(monkeypatch, spy, credits=None):
    """Put the spy where `import betting_ingest` inside the function finds it."""
    monkeypatch.setitem(sys.modules, "betting_ingest", spy)
    # job_heartbeat is imported in a bare try/except at the end; stub it so the
    # test does not write a heartbeat file into the tree.
    hb = types.SimpleNamespace(record=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "job_heartbeat", hb)
    # The shared credit ledger. Stubbed so no test writes a real ledger file,
    # and so a test can drive a refusal without spending a month's budget.
    monkeypatch.setitem(sys.modules, "betting_credits", credits or _Credits())


# --------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------

def test_an_existing_open_snapshot_for_this_slate_blocks_the_paid_call(rm, monkeypatch):
    slate = _slate_now()
    spy = _Spy(existing={"_path": ".cache/odds/" + slate + "-1310.json",
                         "slate_date": slate})
    _install(monkeypatch, spy)

    out = rm.run_odds_open()

    assert spy.run_calls == [], (
        "run_odds_open spent credits on a slate that was already captured; "
        "this is the double-billing the guard exists to prevent")
    assert out["action"] == "skipped_existing"
    assert out["ok"] is True, "a correct skip is a SUCCESS, not a failure"
    assert out["slate"] == slate
    assert slate in out["reason"]


def test_no_snapshot_means_the_capture_actually_happens(rm, monkeypatch):
    spy = _Spy(existing=None)
    _install(monkeypatch, spy)

    out = rm.run_odds_open()

    assert spy.run_calls == ["open"], (
        "the guard is too aggressive: with nothing cached for this slate the "
        "capture must fire, or the cron buys nothing")
    assert out["action"] == "captured"
    assert out["ok"] is True


def test_the_guard_asks_about_the_slate_not_the_box_local_date(rm, monkeypatch):
    """The question the guard asks must be the question the ingest answers.

    betting_ingest stamps each wrapper with a US-Eastern slate date. Asking
    with the BOX's local date would ask a different question on any box not set
    to Eastern, and the deploy box's timezone is undocumented. A fixed -4 hours
    is correct for every slate that has games: the MLB regular season runs
    April through October, which is entirely inside EDT.
    """
    spy = _Spy(existing=None)
    _install(monkeypatch, spy)

    rm.run_odds_open()

    assert spy.latest_calls, "the guard never consulted the cache at all"
    kind, on_date = spy.latest_calls[0]
    assert kind == "open", "the guard filtered on kind=" + repr(kind) + ", not 'open'"
    assert on_date == _slate_now(), (
        "the guard asked about " + repr(on_date) + " but the slate is "
        + repr(_slate_now()))


def test_an_unreadable_cache_refuses_to_spend(rm, monkeypatch):
    """Unknown state is not permission to bill."""
    spy = _Spy(raise_on_latest=True)
    _install(monkeypatch, spy)

    out = rm.run_odds_open()

    assert spy.run_calls == [], (
        "the cache could not be read and run_odds_open billed anyway; an "
        "unreadable cache must never license a second paid pull")
    assert out["ok"] is False
    assert "unreadable" in out["reason"]


def test_an_unarmed_key_skips_for_free_and_reports_success(rm, monkeypatch):
    spy = _Spy(armed=False)
    _install(monkeypatch, spy)

    out = rm.run_odds_open()

    assert spy.run_calls == []
    assert spy.latest_calls == [], (
        "it read the cache before checking whether a key exists; harmless, but "
        "the order should be cheapest-refusal-first")
    assert out["action"] == "skipped_unarmed"
    assert out["ok"] is True, (
        "an unarmed box is a configuration state, not a job failure; a False "
        "here would page somebody every night on a box with no key")


# --------------------------------------------------------------------------
# It is a cron entry point: it must not raise, ever
# --------------------------------------------------------------------------

def test_an_ingest_that_raises_is_reported_not_propagated(rm, monkeypatch):
    class _Boom(_Spy):
        def run(self, kind):
            self.run_calls.append(kind)
            raise RuntimeError("provider returned 502")

    spy = _Boom(existing=None)
    _install(monkeypatch, spy)

    out = rm.run_odds_open()          # must not raise

    assert out["ok"] is False
    assert out["action"] == "failed"
    assert "502" in out["reason"]


def test_a_failed_ingest_status_is_not_reported_as_a_capture(rm, monkeypatch):
    spy = _Spy(existing=None, run_result={"last_run": "error: no events"})
    _install(monkeypatch, spy)

    out = rm.run_odds_open()

    assert out["action"] == "failed", (
        "the ingest reported an error and run_odds_open called it a capture")
    assert out["ok"] is False


# --------------------------------------------------------------------------
# The nightly's fallback must carry the same guard
# --------------------------------------------------------------------------

def test_the_nightly_fallback_guards_on_the_same_slate_question():
    """Step 9d-pre-odds is now a fallback, not the primary. It keeps its guard.

    Source-level, deliberately: the step lives inside the daily branch of a
    ~6000-line entry point that cannot be invoked in a unit test without running
    the pipeline. What is checked is the property that matters - that the step
    asks latest_snapshot(kind="open", on_date=<slate>) BEFORE it can reach
    betting_ingest.run - not the prose around it.
    """
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index('"9d-pre-odds.')
    block = src[i:i + 3200]
    guard = block.index('latest_snapshot(kind="open", on_date=_slate)')
    call = block.index('betting_ingest.run("open")')
    assert guard < call, (
        "step 9d-pre-odds can reach betting_ingest.run without consulting the "
        "cache first, so a nightly running beside the --odds-open cron would "
        "bill a second 3-credit call for a slate already captured")
    assert "timedelta(hours=4)" in block, (
        "the fallback computes its slate some other way than the primary; the "
        "two guards must ask the same question or they do not compose")


def test_the_cron_example_ships_the_open_capture_line():
    """A job nobody installs is worth nothing. This module's own history:
    the close job's crontab line existed for weeks and had never run on any box."""
    ex = (ROOT / "deploy" / "betting-crontab.example").read_text(encoding="utf-8")
    lines = [ln for ln in ex.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")
             and "--odds-open" in ln]
    assert len(lines) == 1, "expected exactly one --odds-open cron line, got " + repr(lines)
    line = lines[0]
    assert line.split()[0:2] == ["10", "13"], (
        "the open capture is not at 13:10 UTC: " + repr(line) + ". 13:10 UTC is "
        "09:10 ET, after the books post openers and more than three hours before "
        "16:16 UTC, the earliest first pitch in the cache. Moving it later "
        "reopens the bug.")
    assert "/etc/eephus.env" in line, (
        "the line does not source the env file, so cron's bare environment will "
        "have no API key and every run will be a silent free no-op that looks "
        "healthy in the log")


def test_the_cron_example_no_longer_advertises_the_removed_card_job():
    ex = (ROOT / "deploy" / "betting-crontab.example").read_text(encoding="utf-8")
    head = ex[:ex.index("SHELL=")]
    assert "card job spends only" not in head, (
        "the header still describes the Card Market cron job, which was removed "
        "with the module on 2026-09-05")


# --------------------------------------------------------------------------
# The shared tier guard (added 2026-09-06 with betting_credits)
# --------------------------------------------------------------------------

def test_the_tier_guard_runs_before_the_call_and_can_refuse(rm, monkeypatch):
    """Four jobs share one 500-credit month. A job that cannot afford its call
    must not make it, and the refusal has to happen BEFORE the request: the
    provider bills on the request, so nothing downstream can undo it."""
    spy = _Spy(existing=None)
    cr = _Credits(allow=False, reason="refused BEFORE the request: open has "
                                      "spent 100 of its 100 monthly credits")
    _install(monkeypatch, spy, cr)

    out = rm.run_odds_open()

    assert spy.run_calls == [], (
        "the tier guard refused and the capture happened anyway")
    assert cr.checks == [("open", 3)], "checked " + repr(cr.checks)
    assert cr.records == [], "a refused call was booked as spend"
    assert out["action"] == "skipped_no_credits"
    assert out["ok"] is True, (
        "an exhausted budget is a budget state, not a job failure; a False "
        "here would page somebody nightly for the rest of the month")


def test_a_successful_capture_is_booked_against_the_tier(rm, monkeypatch):
    spy = _Spy(existing=None)
    cr = _Credits()
    _install(monkeypatch, spy, cr)

    rm.run_odds_open()

    assert spy.run_calls == ["open"]
    assert len(cr.records) == 1, "booked " + repr(cr.records)
    job, cost, _note = cr.records[0]
    assert (job, cost) == ("open", 3)


def test_a_failed_capture_is_still_booked(rm, monkeypatch):
    """The Odds API bills on the REQUEST. A call that reached the provider and
    then raised has already cost its credits, and a ledger that counts only
    successes drifts below the truth exactly when accuracy matters."""
    class _Boom(_Spy):
        def run(self, kind):
            self.run_calls.append(kind)
            raise RuntimeError("provider returned 502")

    spy = _Boom(existing=None)
    cr = _Credits()
    _install(monkeypatch, spy, cr)

    out = rm.run_odds_open()

    assert out["ok"] is False
    assert len(cr.records) == 1, (
        "a request that reached the provider and failed was not booked, so the "
        "ledger now under-counts real spend: " + repr(cr.records))
    assert cr.records[0][0] == "open"


def test_the_duplicate_guard_still_runs_first(rm, monkeypatch):
    """Ordering matters: an already-captured slate must skip for free without
    even consulting the budget, or a cheap no-op looks like a budget event."""
    slate = _slate_now()
    spy = _Spy(existing={"_path": "x.json", "slate_date": slate})
    cr = _Credits()
    _install(monkeypatch, spy, cr)

    out = rm.run_odds_open()

    assert out["action"] == "skipped_existing"
    assert cr.checks == [], (
        "the tier ledger was consulted for a call that was never going to "
        "happen")
    assert cr.records == []


def test_a_broken_credit_ledger_does_not_stop_the_job(rm, monkeypatch):
    """The ledger is a safety rail added on 2026-09-06. A job that ran fine
    before it existed must not start failing because the rail broke."""
    class _BadCredits(_Credits):
        def check(self, job, cost, **kw):
            raise RuntimeError("ledger file is corrupt")

    spy = _Spy(existing=None)
    _install(monkeypatch, spy, _BadCredits())

    out = rm.run_odds_open()

    assert spy.run_calls == ["open"], (
        "a broken credit ledger blocked a capture; the rail must fail open, "
        "because the alternative is losing an unrecoverable opening price to "
        "a bookkeeping bug")
    assert out["ok"] is True


def test_the_close_job_carries_the_same_guard():
    """Source-level: the close job cannot be invoked without a slate and a
    schedule. What is checked is that its guard precedes its call."""
    src = (ROOT / "tools" / "betting_close_job.py").read_text(encoding="utf-8")
    chk = src.index('_bc.check("close"')
    call = src.index('bi.run("close")')
    assert chk < call, (
        "tools/betting_close_job.py can reach betting_ingest.run before "
        "checking the shared credit tier")
    assert "_book_close_credits" in src, (
        "the close job spends 3 credits a call and books none of them, so the "
        "shared ledger under-counts by about 93 a month")


def test_the_props_pull_checks_both_budgets():
    """Props has its own owner-set cap AND competes for the shared tier. Being
    inside one is not being inside the other."""
    src = (ROOT / "betting_ingest.py").read_text(encoding="utf-8")
    i = src.index("ok, reason = props_budget_check(")
    block = src[i:i + 1400]
    assert '_bc.check("props"' in block, (
        "the props pull consults only its own cap, so it can spend the shared "
        "tier out from under the open and close captures while reporting "
        "itself comfortably inside budget")
    fetch = src.index("fetch_props_event(eid", i)
    assert i < fetch


def test_every_job_that_bills_has_an_allocation():
    """A job the ledger cannot account for is refused by `check`, so a new
    paid job must be added to ALLOCATIONS or it silently stops working."""
    import betting_credits as bc
    assert set(bc.ALLOCATIONS) == {"open", "close", "props", "futures"}
    assert sum(bc.ALLOCATIONS.values()) < bc.TIER_MONTHLY, (
        "the per-job allocations consume the whole tier, leaving no reserve "
        "for the spend this ledger cannot see (a manual pull, a second box, a "
        "retry that billed before it failed)")


# --------------------------------------------------------------------------
# The empty-market credit trap
# --------------------------------------------------------------------------

def test_a_request_asking_for_no_markets_costs_nothing():
    """THE TRAP THIS CLOSES, and it has real money on it.

    `credits_for` floors both factors at 1 so that a one-market call is not
    free. Those floors used to apply to the EMPTY case too, so
    credits_for((), ("us",)) returned 1. Any capture job that ships inert with
    an empty market tuple and is armed later would then clear its own credit
    guard, because betting_credits.check short-circuits only at cost <= 0,
    issue a request asking for nothing, and book a real credit every run.

    Zero markets means no call.
    """
    import betting_ingest as bi
    assert bi.credits_for((), ("us",)) == 0
    assert bi.credits_for((), ()) == 0
    assert bi.credits_for(("h2h",), ()) == 0


def test_the_floors_still_apply_to_every_non_empty_call():
    """The fix must not make a one-market call free, which is what the floors
    were there for."""
    import betting_ingest as bi
    assert bi.credits_for(("h2h",), ("us",)) == 1
    assert bi.credits_for(("h2h", "spreads", "totals"), ("us",)) == 3
    assert bi.credits_for() == 3


def test_the_zero_cost_short_circuit_is_what_makes_the_fix_load_bearing():
    """The two halves have to be read together: check() treats a zero cost as
    free, so credits_for is the only thing standing between an empty market
    tuple and a billed request."""
    import betting_credits as bc
    ok, why = bc.check("props", 0)
    assert ok and "spends nothing" in why
