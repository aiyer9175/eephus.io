# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""data/betting_learning.json: what the module learned since yesterday.

WHY THIS EXISTS. The betting module claims it improves each day. Three things
genuinely do move on their own - the vintage-graded sample, the settled paper
prices, and now the calibration ledger - and NONE of them was published as a
series, so "improving" was a claim with no time axis behind it. A reader could
see today's gate table and had no way to tell whether it had moved in a month.

THE THREE PROPERTIES THAT MAKE THIS AN INSTRUMENT AND NOT A PROGRESS BAR. All
three are required, and any one of them missing turns the file into marketing:

  1. `days_to_need` IS A MEASURED RATE APPLIED FORWARD, AND IT SAYS SO. Every
     projection carries `rate`, `rate_basis` and `is_projection: true`. The rate
     is counted off the last 28 dates of actual arrivals, not assumed from a
     162-game schedule, because the box does not capture every night and the
     schedule is not the thing that determines how fast this clock ticks.
  2. HISTORY IS NEVER REWRITTEN. Past rows go through the same
     `betting_export.check_append_only` seam the public record uses. A series
     whose old points can be edited cannot show that anything improved: it can
     only show what today wants yesterday to have looked like.
  3. A COUNTER THAT CAN GO BACKWARDS IS ALLOWED TO RENDER GOING BACKWARDS. The
     vintage sample shrinks when a refit changes the eligible window; a Brier
     gets worse; a tag's settled count drops when a game is voided. None of
     those are smoothed, floored or carried forward. `direction` on each clock
     reports the sign of the change since the previous row, including "down".

WHAT IS IN IT
  latest.clocks        the three clocks, numerator / denominator / measured rate
  latest.gates         the gate table VERBATIM from betting_model.min_edge_gate
  latest.skill         vintage and forward Brier against the home-field baseline
  latest.calibration   ten bins from the calibration ledger
  latest.market_move   the closing-move block, with blocked_by when it is empty
  latest.by_market     the per-market split
  latest.dispersion    the run-dispersion verdict
  history              one small row per nightly, capped at 400

WHAT IT IS NOT. It is not a record of bets, it publishes no ROI, and the
calibration section is NOT gate 1. Gate 1 is the vintage-graded moneyline sample
beating the home-field baseline out of sample. A calibrated board says the
probabilities are honest; it does not say they beat a constant.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("betting_learning")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
LEARNING_PATH = DATA_DIR / "betting_learning.json"

#: How many nightly rows the series keeps. 400 is a little over two seasons of
#: daily rows, which is long enough that a gate opening is still visible next to
#: the year it was closed, and small enough that the file stays a page fetch.
HISTORY_CAP = 400

#: The window every measured rate is counted over. 28 dates, because the two
#: clocks tick on slate days and four weeks is the shortest window that survives
#: a rained-out weekend without the rate swinging by half.
RATE_WINDOW_DATES = 28


class LearningSeriesError(RuntimeError):
    """A write would have rewritten a past row."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# the append-only series
# ---------------------------------------------------------------------------
def load(path: Path | None = None) -> dict:
    """The artifact, or an empty shell. An UNREADABLE file raises, on the same
    reasoning as the two ledgers: returning a blank series would hand the next
    write an empty history to append to and erase the record silently."""
    p = Path(path or LEARNING_PATH)
    if not p.exists():
        return {"history": []}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LearningSeriesError(
            f"{p.name} exists but will not parse ({exc}); refusing to treat an "
            "unreadable series as an empty one") from exc
    if not isinstance(obj, dict):
        raise LearningSeriesError(f"{p.name} is not a JSON object")
    obj.setdefault("history", [])
    return obj


def merge_history(existing: list[dict], today_row: dict, *,
                  cap: int = HISTORY_CAP,
                  on_disk: list[dict] | None = None) -> tuple[list[dict], dict]:
    """`existing` + today, with every PAST row proved unchanged against disk.

    Today's row may be replaced (a nightly can re-run, and the second run knows
    more than the first). Every EARLIER row may not, and that is proved with the
    public record's own `betting_export.check_append_only` rather than by a
    second implementation of the same rule.

    `on_disk` is the history re-read immediately before the write. The check is
    then a real comparison and not a tautology: it catches a past row this
    process edited, AND it catches another process having appended between the
    build and the write, because the disk prefix would then be longer than the
    one being proposed and `check_append_only` refuses a shrink.

    THE CAP IS APPLIED AFTER THE CHECK AND COUNTED. Trimming the oldest rows is
    a deletion, so it cannot hide inside an append-only guarantee: the check
    proves nothing was EDITED, the cap then drops from the front, and the number
    dropped is returned so the caller can publish it."""
    today = today_row.get("date")
    if not today:
        raise LearningSeriesError("today's row carries no date")
    past = [r for r in existing if r.get("date") != today]
    if past != existing[:len(past)]:
        raise LearningSeriesError(
            f"a row dated {today} sits in the middle of the history; the series "
            "is ordered by date and only the last row may be today's")

    baseline = existing if on_disk is None else list(on_disk)
    past_on_disk = [r for r in baseline if r.get("date") != today]

    from betting_export import check_append_only
    check_append_only(past_on_disk, past)

    proposed = past + [today_row]
    dropped = max(0, len(proposed) - cap)
    return proposed[dropped:], {"n_dropped_by_cap": dropped, "cap": cap}


def _write(obj: dict, path: Path | None = None) -> None:
    p = Path(path or LEARNING_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
        try:
            from storage import _atomic_replace
        except Exception:                                       # noqa: BLE001
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


# ---------------------------------------------------------------------------
# measured rates
# ---------------------------------------------------------------------------
def _dates_back(n: int = RATE_WINDOW_DATES) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=n)).isoformat()


def measured_rate(counts_by_date: dict, *, window: int = RATE_WINDOW_DATES,
                  series_start: str | None = None) -> dict:
    """Arrivals per CALENDAR DAY over the window, counted not assumed.

    The denominator is calendar days, NOT the number of dates that happened to
    produce a row. That is the conservative choice and it is the right one: a
    night the box did not capture is a night the clock did not tick, and
    dividing by "dates with arrivals" would report the rate on the days it
    worked and then apply it to every day.

    BUT ONLY THE DAYS THE SERIES COULD HAVE SEEN (fixed 2026-08-16). The old
    denominator was the full window unconditionally, so a series younger than
    the window divided a few days of arrivals by 28: on the vintage clock, 19
    arrivals over a 4-day diffable span published as 0.68 a day against a true
    ~4.75, and the 504-day ETA in the 2026-08-16 artifact was that arithmetic,
    not a measurement (tools/betting_clock_probe.py holds the decomposition).
    The denominator is now min(window, series age in days), the age is
    published beside the rate, and per_day_28d keeps the full-window figure so
    the fix can never read as the module having sped up.

    `series_start` is the first date the series could have recorded an arrival
    on; without it the earliest date in `counts_by_date` stands in, which
    understates the age for a differenced series (the first point has no
    predecessor to difference against) and so can only make the rate higher,
    never lower, than the honest one."""
    cutoff = _dates_back(window)
    hit = {d: n for d, n in (counts_by_date or {}).items()
           if d and d >= cutoff}
    total = sum(hit.values())
    start = series_start or min((d for d in (counts_by_date or {}) if d),
                                default=None)
    age = None
    if start:
        try:
            age = max(1, (datetime.now(timezone.utc).date()
                          - date.fromisoformat(str(start)[:10])).days + 1)
        except ValueError:
            age = None
    effective = min(window, age) if age else window
    basis = (f"arrivals over the {window} calendar days since {cutoff}, divided "
             f"by {effective} day(s); a night with no capture counts as zero")
    if age is not None and effective < window:
        basis += (f". The series is only {age} day(s) old (started {start}), so "
                  "days before it are not counted")
    basis += "."
    return {
        "n_in_window": total,
        "n_dates_with_arrivals": len(hit),
        "window_days": window,
        "window_from": cutoff,
        "series_start": start,
        "series_age_days": age,
        "effective_window_days": effective,
        "per_day": (round(total / effective, 4) if effective else None),
        # The pre-2026-08-16 figure, kept so the denominator fix is visible as
        # a fix and can never be mistaken for the module speeding up.
        "per_day_28d": (round(total / window, 4) if window else None),
        "basis": basis,
    }


def days_to_need(have, need, rate: dict) -> dict:
    """How many days the MEASURED rate would take to cover the shortfall.

    Says out loud that it is a projection. Returns None with a `blocked_by` when
    the rate is zero, which is the honest answer to "when" when the answer is
    "never, at the rate actually observed"."""
    try:
        have_i, need_i = int(have or 0), int(need or 0)
    except (TypeError, ValueError):
        return {"days": None, "is_projection": True,
                "blocked_by": "the clock's numerator or denominator is not a count"}
    short = max(0, need_i - have_i)
    per_day = rate.get("per_day") or 0.0
    if short == 0:
        return {"days": 0, "is_projection": False,
                "note": "already at or past the requirement"}
    if per_day <= 0:
        return {"days": None, "is_projection": True, "rate": per_day,
                "rate_basis": rate.get("basis"),
                "blocked_by": (f"no arrivals in the last {rate.get('window_days')} "
                               "days, so no measured rate exists to project with; "
                               "the null is the absence of an estimate.")}
    return {
        "days": int(math.ceil(short / per_day)),
        "short_by": short,
        "rate": per_day,
        "rate_basis": rate.get("basis"),
        "is_projection": True,
        "note": ("a MEASURED arrival rate applied forward, not a schedule. It "
                 "assumes the next weeks look like the last ones."),
    }


def _direction(now, before) -> str:
    """up / down / flat / new. `down` is a legal, publishable answer."""
    if before is None:
        return "new"
    if now is None:
        return "unknown"
    try:
        d = float(now) - float(before)
    except (TypeError, ValueError):
        return "unknown"
    if abs(d) < 1e-12:
        return "flat"
    return "up" if d > 0 else "down"


# ---------------------------------------------------------------------------
# the blocks
# ---------------------------------------------------------------------------
def _vintage_clock(evald: dict, history: list[dict]) -> dict:
    """Gate 1's clock: vintage-graded games toward the 600 the sweep needs.

    THE RATE IS MEASURED FROM THIS FILE'S OWN HISTORY when it has two points,
    because that is the only record of how fast the sample ACTUALLY grew on this
    box. Before there are two points it falls back to the eval's own graded date
    span, and says which basis it used."""
    v = (evald or {}).get("vintage") or {}
    have = int(v.get("n_graded") or 0)
    need = int(v.get("min_graded_games_for_min_edge") or 600)

    counts, basis, start = {}, None, None
    pts = [(r.get("date"), r.get("vintage_n_graded")) for r in history
           if r.get("date") and r.get("vintage_n_graded") is not None]
    if len(pts) >= 2:
        basis = "this file's own history"
        # The series began at its FIRST row, not at the first differenced
        # arrival: the first row has no predecessor to difference against, so
        # min(counts) would understate the age by one row.
        start = pts[0][0]
        for (d0, n0), (d1, n1) in zip(pts, pts[1:]):
            counts[d1] = max(0, int(n1) - int(n0))
    else:
        first, last = v.get("first_graded_date"), v.get("last_graded_date")
        if first and last and have:
            try:
                span = max(1, (date.fromisoformat(last) - date.fromisoformat(first)).days + 1)
            except ValueError:
                span = 1
            basis = (f"the eval's own graded span ({first} to {last}, {span} days, "
                     f"{have} games), spread evenly, because this series has fewer "
                     "than two history points to difference")
            start = first
            per = have / span
            d = date.fromisoformat(last)
            for i in range(min(span, RATE_WINDOW_DATES)):
                counts[(d - timedelta(days=i)).isoformat()] = per

    rate = measured_rate(counts, series_start=start)
    rate["basis"] = f"{rate['basis']} Source: {basis}." if basis else rate["basis"]
    prev = next((r.get("vintage_n_graded") for r in reversed(history)
                 if r.get("vintage_n_graded") is not None), None)
    return {
        "id": "vintage_sample",
        "question": "has the model been graded on enough games it could not see",
        "have": have, "need": need,
        "pct": (round(have / need, 4) if need else None),
        "rate": rate,
        "eta": days_to_need(have, need, rate),
        "direction": _direction(have, prev),
        "n_gradable": v.get("n_gradable"),
        "n_skipped_no_vintage": v.get("n_skipped_no_vintage"),
        "first_graded_date": v.get("first_graded_date"),
        "last_graded_date": v.get("last_graded_date"),
        "may_go_backwards": ("yes. A refit can change which games are eligible; "
                             "a drop is shown, not held at the high-water mark."),
    }


def _gradable_clock(evald: dict, history: list[dict]) -> dict:
    """The archive clock: gradable games toward the ~900 the 600-game gate
    implies. New 2026-08-16.

    THIS IS THE CLOCK THE RUNBOOK'S ETA TABLE RUNS ON. n_graded counts only
    EVAL-window games: the fit window holds the first VINTAGE_FIT_TARGET_GAMES
    (300) of the archive, clamped to half the covered dates while the archive
    is short, so the eval window cannot hold 600 graded games until roughly
    900 are gradable. Watching n_graded alone therefore makes the module look
    about half as fast as the archive is actually growing, on top of which the
    fit boundary eats the early half of every new stretch of dates. Publishing
    the archive's own numerator, need and measured rate here is what lets
    docs/diamond-betting.md's ETA table and this artifact do the same
    arithmetic on the same numbers instead of disagreeing."""
    v = (evald or {}).get("vintage") or {}
    have = int(v.get("n_gradable") or 0)
    try:
        import betting_model as bm
        graded_need = int(bm.VINTAGE_MIN_GRADED_GAMES)
        fit_target = int(bm.VINTAGE_FIT_TARGET_GAMES)
    except Exception:                                           # noqa: BLE001
        graded_need, fit_target = 600, 300
    need = graded_need + fit_target

    counts, basis, start = {}, None, None
    pts = [(r.get("date"), r.get("vintage_n_gradable")) for r in history
           if r.get("date") and r.get("vintage_n_gradable") is not None]
    if len(pts) >= 2:
        basis = "this file's own history"
        start = pts[0][0]
        for (d0, n0), (d1, n1) in zip(pts, pts[1:]):
            counts[d1] = max(0, int(n1) - int(n0))
    else:
        first, last = v.get("first_graded_date"), v.get("last_graded_date")
        if first and last and have:
            try:
                span = max(1, (date.fromisoformat(last) - date.fromisoformat(first)).days + 1)
            except ValueError:
                span = 1
            basis = (f"the eval's own gradable span ({first} to {last}, {span} "
                     f"days, {have} games), spread evenly, because this series "
                     "has fewer than two gradable-count history points to "
                     "difference")
            start = first
            per = have / span
            d = date.fromisoformat(last)
            for i in range(min(span, RATE_WINDOW_DATES)):
                counts[(d - timedelta(days=i)).isoformat()] = per

    rate = measured_rate(counts, series_start=start)
    rate["basis"] = f"{rate['basis']} Source: {basis}." if basis else rate["basis"]
    prev = next((r.get("vintage_n_gradable") for r in reversed(history)
                 if r.get("vintage_n_gradable") is not None), None)
    return {
        "id": "gradable_games",
        "question": ("how fast is the archive itself growing toward the "
                     "gradable total the 600-graded gate implies"),
        "have": have, "need": need,
        "need_derivation": (f"{graded_need} eval-window games for gate 1 plus "
                            f"the {fit_target}-game fit window in front of them "
                            "(VINTAGE_MIN_GRADED_GAMES + VINTAGE_FIT_TARGET_GAMES)"),
        "pct": (round(have / need, 4) if need else None),
        "rate": rate,
        "eta": days_to_need(have, need, rate),
        "direction": _direction(have, prev),
        "why_beside_vintage_sample": ("n_graded is the eval window only; the fit "
                                      "window absorbs roughly half of a short "
                                      "archive's growth, so the graded clock "
                                      "understates how fast the archive fills. "
                                      "This clock is the archive itself."),
        "may_go_backwards": ("yes, for the same reason as the vintage clock: a "
                             "refit or a coverage change can shrink the "
                             "gradable set, and the drop is rendered."),
    }


def _price_clock(shadow_summary: dict, ledger_rows: list[dict],
                 history: list[dict]) -> dict:
    """Gate 3's clock, PER TAG. Four clocks, not one.

    Section 7a forbids pooling the tags, so there is no single number here and
    there should not be. The cost is stated: each tag needs its own 100 settled
    rows, so the slowest tag is roughly 3x slower to open than the pooled
    count it replaces, and the uncapped `board_all` tag exists to pay that bill.
    """
    readiness = (shadow_summary or {}).get("sweep_readiness") or {}
    need = int((shadow_summary or {}).get("min_bets_for_sweep") or 100)

    try:
        import betting_shadow
        _tags_of = betting_shadow.row_tags
    except Exception:                                           # noqa: BLE001
        def _tags_of(r):
            return {r.get("slot") or "untagged"}

    # One pass over the ledger, indexed by tag, rather than one pass per tag.
    settled_by_tag_date: dict[str, dict] = {}
    for r in ledger_rows:
        if r.get("result") not in ("won", "lost"):
            continue
        d = r.get("slate_date")
        if not d:
            continue
        for t in _tags_of(r):
            settled_by_tag_date.setdefault(t, {})
            settled_by_tag_date[t][d] = settled_by_tag_date[t].get(d, 0) + 1

    per_tag = {}
    for tag, block in sorted(readiness.items()):
        rate = measured_rate(settled_by_tag_date.get(tag) or {})
        prev = next((((r.get("price_clock") or {}).get(tag) or {}).get("have")
                     for r in reversed(history)
                     if isinstance(r.get("price_clock"), dict)
                     and tag in (r.get("price_clock") or {})), None)
        per_tag[tag] = {
            "have": block.get("n"), "need": need,
            "ready": block.get("ready"),
            "max_per_slate": block.get("max_per_slate"),
            "rate": rate,
            "eta": days_to_need(block.get("n"), need, rate),
            "direction": _direction(block.get("n"), prev),
        }
    return {
        "id": "graded_price_history",
        "question": ("does any edge threshold clear an ROI lower bound of zero, "
                     "measured PER SELECTION RULE"),
        "need_per_tag": need,
        "by_tag": per_tag,
        "why_per_tag": ("docs/diamond-betting.md section 7a: a pooled ROI measures "
                        "a mixture nobody bet. The tags select on different "
                        "quantities, so a threshold fitted to their union is wrong "
                        "for each of them."),
        "cost": (f"{need} settled rows PER TAG, so the slowest tag opens about 3x "
                 "slower than the pooled count would. The uncapped board_all tag "
                 "carries that cost; no existing tag is loosened."),
    }


def _calibration_block(cal_summary: dict, history: list[dict]) -> dict:
    """Ten bins from the calibration ledger, plus its own arrival clock.

    THIS IS NOT GATE 1 and the field says so in the artifact, not only here."""
    n_settled = int((cal_summary or {}).get("n_settled") or 0)
    prev = next((r.get("calibration_n_settled") for r in reversed(history)
                 if r.get("calibration_n_settled") is not None), None)
    bins = (cal_summary or {}).get("bins") or []
    pooled = (cal_summary or {}).get("pooled") or {}
    blocked = None
    if not n_settled:
        blocked = ("the calibration ledger has no settled rows yet. It fills at "
                   "roughly 44 priced sides a slate day once the nightly records "
                   "it, and every one of them settles the next morning.")
    return {
        "n_rows": (cal_summary or {}).get("n_rows"),
        "n_settled": n_settled,
        "n_open": (cal_summary or {}).get("n_open"),
        "n_push": (cal_summary or {}).get("n_push"),
        "n_slate_days": (cal_summary or {}).get("n_slate_days"),
        "brier": pooled.get("brier"),
        "log_loss": pooled.get("log_loss"),
        "mean_model_prob": pooled.get("mean_model_prob"),
        "mean_market_fair_prob": pooled.get("mean_market_fair_prob"),
        "hit_rate": pooled.get("hit_rate"),
        "bins": bins,
        "direction": _direction(n_settled, prev),
        "blocked_by": blocked,
        "not_gate_1": ("calibration is NOT the model's first validation gate. Gate "
                       "1 is the vintage-graded moneyline sample beating the "
                       "home-field baseline on games the model could not see. "
                       "Good calibration does not license a bet."),
    }


def _skill_block(evald: dict) -> dict:
    """The Brier margin over the home-field baseline, in both vintages.

    BOTH ARE REPORTED because they disagree and the disagreement is the point:
    the forward split beats the baseline on contaminated features and the
    vintage split does not beat it at all. Publishing only the first would be
    quoting the number that leaks."""
    out = {}
    for key in ("vintage", "forward", "in_sample"):
        b = (evald or {}).get(key) or {}
        s = b.get("skill_vs_home_base") or {}
        out[key] = {
            "label": b.get("label"), "mode": b.get("mode"), "honest": b.get("honest"),
            "n": b.get("n"), "brier": b.get("brier"),
            "brier_home_base": b.get("brier_home_base"),
            "delta": s.get("delta"), "sd": s.get("sd"), "t": s.get("t"),
            "beats_baseline_95": s.get("beats_baseline_95"),
            "n_for_95": s.get("n_for_95"),
        }
    out["note"] = ("only the `vintage` row is out of sample. `forward` removes "
                   "coefficient leakage and keeps feature leakage, and `in_sample` "
                   "keeps both. n_for_95 is null wherever the point estimate is "
                   "negative: no sample size makes a negative margin detectable.")
    return out


#: Where the close job proves it ran, and what its last calibration attach
#: did. Written by tools/betting_close_job.py, read here. Both live under
#: .cache/ because deploy/nightly-build.sh runs `git checkout -- .` before the
#: build, so a tracked stamp would be reverted before this could read it.
CLOSE_JOB_HEARTBEAT_PATH = ROOT / ".cache" / "betting" / "close_job_heartbeat.json"
CLOSE_ATTACH_RESULT_PATH = ROOT / ".cache" / "betting" / "close_attach_result.json"


def _market_move_block(cal_summary: dict) -> dict:
    """The market's own open-to-close move on the sides the ledger priced.

    `blocked_by` is filled whenever it is empty, because an empty CLV-shaped
    block with no explanation reads as "no edge" rather than "not measured yet".
    NEVER pooled with the published record's clv_pct: this ledger holds no
    positions, so nothing here is closing line VALUE.

    THE EMPTY-CASE DIAGNOSIS USED TO BE WRONG TWICE OVER (fixed 2026-08-16).
    It named data/betting_clv.json as the missing repair, but that file is the
    published record's CLV sidecar and no calibration row is built from it,
    so its absence explained nothing and its presence repaired nothing. Worse,
    whenever the sidecar happened to exist, the block asserted that closes
    "matched no open row at the same book", a book-mismatch measurement that
    had never run: append_close had no production caller, so nothing had ever
    been matched or mismatched. The block now walks the chain that actually
    fills it, in order: the close job (tools/betting_close_job.py, which a
    cron must reach), the close snapshot ingest, betting_export.
    close_events_for_calibration, betting_calibration.append_close. And it
    claims a book mismatch only off a PERSISTED close-attach result, never
    from inference."""
    mm = (cal_summary or {}).get("market_move_pct") or {}
    n = int(mm.get("n") or 0)
    blocked = None
    if not n:
        hb = _load_json(CLOSE_JOB_HEARTBEAT_PATH)
        attach = _load_json(CLOSE_ATTACH_RESULT_PATH)
        if (isinstance(attach, dict) and int(attach.get("n_book_mismatch") or 0) > 0
                and not int(attach.get("closed") or 0)):
            blocked = (f"append_close ran and attached nothing: the persisted "
                       f"attach result for slate {attach.get('slate_date')} "
                       f"({attach.get('written_at')}) reports "
                       f"{int(attach['n_book_mismatch'])} book mismatch(es) and "
                       f"0 attached. A close taken at a different book is a "
                       "different market, not a move.")
        elif isinstance(attach, dict):
            blocked = (f"the close job has run its calibration attach for slate "
                       f"{attach.get('slate_date')} ({int(attach.get('closed') or 0)} "
                       f"attached, {int(attach.get('n_no_close') or 0)} row(s) with "
                       "no close price at the open row's book) but no market move "
                       "has reached the ledger summary yet.")
        elif hb is None:
            blocked = ("the close job has never run on this machine: no cron or "
                       "scheduled task reaches tools/betting_close_job.py, so the "
                       "chain that fills this block (close job, then close "
                       "snapshot ingest, then betting_export."
                       "close_events_for_calibration, then betting_calibration."
                       "append_close) stops at its first link. Install "
                       "deploy/betting-crontab.example (Linux) or "
                       "deploy/betting-close-task.ps1 -Register (Windows), then "
                       "confirm with `python tools/betting_close_job.py "
                       "--selfcheck`.")
        else:
            blocked = (f"the close job is scheduled (last ran "
                       f"{hb.get('last_run_utc')}, decision: {hb.get('reason')}) "
                       "but it has not yet fired and persisted a close-attach "
                       "result for any slate; whether a close matches the open "
                       "row's book cannot be known until one exists.")
    return {
        "n": n, "mean_pct": mm.get("mean"),
        "share_positive": mm.get("share_positive"),
        "blocked_by": blocked,
        "name_note": ("called market_move_pct and never clv_pct. CLV is a property "
                      "of a position taken at a price; the calibration ledger holds "
                      "no positions, so the two may never be pooled."),
    }


def _dispersion_block(evald: dict) -> dict:
    """The negative-binomial run-dispersion arm's verdict, as decided."""
    d = (evald or {}).get("run_dispersion") or {}
    return {
        "status": d.get("status"), "passed": d.get("passed"),
        "served": d.get("served"), "alpha": d.get("alpha"),
        "served_alpha": d.get("served_alpha"),
        "n_fit": d.get("n_fit"), "n_eval_games": d.get("n_eval_games"),
        "moneyline_brier": d.get("moneyline_brier"),
        "runline_logloss": d.get("runline_logloss"),
        "total_logloss": d.get("total_logloss"),
        "mode": d.get("mode"),
        "verdict": ("SHIPPED" if d.get("served") else
                    ("ran and did not pass" if d.get("status") == "ran"
                     else (d.get("status") or "not run"))),
    }


# ---------------------------------------------------------------------------
# build + write
# ---------------------------------------------------------------------------
def build(*, path: Path | None = None) -> dict:
    """Assemble today's block. Reads only; writes nothing."""
    series = load(path)
    history = list(series.get("history") or [])

    evald = _load_json(DATA_DIR / "betting_model_eval.json") or {}

    shadow_summary, ledger_rows = {}, []
    try:
        import betting_shadow
        shadow_summary = betting_shadow.summary()
        ledger_rows = betting_shadow.load()
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_learning: shadow ledger unavailable (%s)", exc)

    cal_summary = {}
    try:
        from tools import betting_calibration
        cal_summary = betting_calibration.summary()
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_learning: calibration ledger unavailable (%s)", exc)

    # THE GATE IS RECOMPUTED AT BUILD TIME, NOT COPIED FROM THE EVAL ARTIFACT
    # (2026-08-16). The eval artifact's min_edge_gate block freezes at model
    # refit time while the shadow ledger keeps settling, so the two drift
    # inside one artifact: on 2026-08-16 the eval's gate said board_all had 47
    # settled rows while the clocks below, reading the live ledger the same
    # night, said 72. Same quantity, two denominators, one file. The gate is
    # now always recomputed against the ledger as it stands and stamped
    # computed_at, and the eval artifact's copy is kept beside it as
    # gates_as_of_eval so the drift itself stays visible instead of choosing a
    # winner silently. The eval copy is served only when the recompute is
    # impossible, and the block says so.
    gate_as_of_eval = (evald or {}).get("min_edge_gate") or {}
    gate, gate_computed_at, gate_basis = {}, None, None
    try:
        import betting_model as bm
        gate = bm.min_edge_gate((evald or {}).get("vintage"))
        gate_computed_at = _now()
        gate_basis = "recomputed against the ledger at build time"
    except Exception as exc:                                    # noqa: BLE001
        log.warning("betting_learning: gate recompute unavailable (%s); "
                    "serving the eval artifact's copy", exc)
        gate = gate_as_of_eval
        gate_basis = ("the eval artifact's copy; the recompute was unavailable, "
                      "so these counts are as of the last model refit")

    vintage_clock = _vintage_clock(evald, history)
    gradable_clock = _gradable_clock(evald, history)
    price_clock = _price_clock(shadow_summary, ledger_rows, history)
    calibration = _calibration_block(cal_summary, history)

    latest = {
        "date": _today(),
        "generated_at": _now(),
        "eval_generated_at": evald.get("generated_at"),
        "model_version": evald.get("model_version"),
        "clocks": {"vintage_sample": vintage_clock,
                   "gradable_games": gradable_clock,
                   "graded_price_history": price_clock},
        # VERBATIM. The gate table is the model's own statement about itself
        # and is copied, not paraphrased: a summary here that drifted from the
        # gate would be a second, quieter claim about the same thing. Since
        # 2026-08-16 it is min_edge_gate's output recomputed at build time
        # rather than the eval artifact's frozen copy; see the comment above
        # gate_as_of_eval for the 47-vs-72 drift that forced the change.
        "gates": {"min_edge": gate.get("min_edge"),
                  "all_gates_open": gate.get("all_gates_open"),
                  "gates": gate.get("gates"),
                  "odds_snapshot_dates": gate.get("odds_snapshot_dates"),
                  "sweep": gate.get("sweep"),
                  "policy": gate.get("policy"),
                  "verbatim_from": "betting_model.min_edge_gate",
                  "computed_at": gate_computed_at,
                  "gate_basis": gate_basis,
                  "gates_as_of_eval": ({
                      "as_of": evald.get("generated_at"),
                      "min_edge": gate_as_of_eval.get("min_edge"),
                      "all_gates_open": gate_as_of_eval.get("all_gates_open"),
                      "gates": gate_as_of_eval.get("gates"),
                      "sweep": gate_as_of_eval.get("sweep"),
                      "note": ("the eval artifact's own copy, frozen at refit "
                               "time. Its counts may trail the recomputed "
                               "block because the ledger keeps settling after "
                               "the refit; the drift is published, not "
                               "resolved."),
                  } if gate_as_of_eval else None)},
        "skill": _skill_block(evald),
        "calibration": calibration,
        "market_move": _market_move_block(cal_summary),
        "by_market": (cal_summary or {}).get("by_market"),
        "dispersion": _dispersion_block(evald),
        "shadow_by_tag": (shadow_summary or {}).get("by_tag"),
        "shadow_by_slot": (shadow_summary or {}).get("by_slot"),
        "honesty": [
            "every days_to_need is a MEASURED arrival rate applied forward, and "
            "each one carries the window it was counted over",
            "history rows for past dates are never rewritten; they go through the "
            "public record's own check_append_only seam",
            "any counter here may go backwards, and is rendered going backwards "
            "rather than carried forward at its high-water mark",
        ],
    }

    history_row = {
        "date": latest["date"],
        "generated_at": latest["generated_at"],
        "vintage_n_graded": vintage_clock["have"],
        # The archive counter, stored so the gradable clock can difference its
        # own history the way the vintage clock does (new 2026-08-16; the
        # clock runs on the eval-span fallback until two rows carry it).
        "vintage_n_gradable": gradable_clock["have"],
        "vintage_need": vintage_clock["need"],
        "vintage_brier": ((evald.get("vintage") or {}).get("brier")),
        "vintage_skill_t": (((evald.get("vintage") or {}).get("skill_vs_home_base")
                             or {}).get("t")),
        "price_clock": {t: {"have": b.get("have"), "ready": b.get("ready")}
                        for t, b in (price_clock.get("by_tag") or {}).items()},
        "calibration_n_rows": calibration.get("n_rows"),
        "calibration_n_settled": calibration.get("n_settled"),
        "calibration_brier": calibration.get("brier"),
        "market_move_n": (latest["market_move"] or {}).get("n"),
        "all_gates_open": gate.get("all_gates_open"),
        "min_edge": gate.get("min_edge"),
    }
    return {"latest": latest, "history_row": history_row, "history": history}


def run(*, path: Path | None = None, log_fn=None) -> dict:
    """Build today's block and append it. The nightly's entry point."""
    built = build(path=path)
    # Re-read immediately before the write, so `check_append_only` compares the
    # proposal against what is on disk NOW rather than against what it was when
    # the block was assembled.
    fresh = load(path)
    merged, cap_info = merge_history(list(built["history"]),
                                     built["history_row"],
                                     on_disk=list(fresh.get("history") or []))
    out = {
        "generated_at": built["latest"]["generated_at"],
        "what": ("what the betting module learned since yesterday: two clocks, the "
                 "gate table, the calibration ledger and the closing-move block. "
                 "No bets, no ROI, no recommendation."),
        "history_cap": cap_info["cap"],
        "n_history": len(merged),
        "n_history_dropped_this_write": cap_info["n_dropped_by_cap"],
        "latest": built["latest"],
        "history": merged,
    }
    _write(out, path)
    if log_fn:
        v = built["latest"]["clocks"]["vintage_sample"]
        cal = built["latest"]["calibration"]
        log_fn(f"betting_learning: vintage {v['have']}/{v['need']} "
               f"({v['direction']}), calibration {cal['n_settled']} settled, "
               f"{len(merged)} history row(s)")
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print without writing")
    args = ap.parse_args(argv)
    if args.dry_run:
        print(json.dumps(build()["latest"], indent=1, default=str))
        return 0
    out = run(log_fn=print)
    print(json.dumps({k: v for k, v in out.items() if k != "history"},
                     indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
