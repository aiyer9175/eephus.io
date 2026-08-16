# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Decompose the 19x gap between how fast games actually arrive and how fast
the vintage clock said they do. Read-only: writes nothing, spends nothing.

THE QUESTION. MLB completes ~13.1 games per calendar date and the archive was
measured growing at ~12.4, yet data/betting_learning.json published the
vintage clock at 0.68 graded games per day and a 504-day ETA to the 600-game
gate. That is a ~19x gap between the world and the instrument, and a gap that
size is never one bug. This probe measures where every factor of it lives:

  (i)   SERIES-YOUTH DENOMINATOR INFLATION. measured_rate divided by the full
        28-day window while the learning series was days old. Two named
        artifacts: arrivals predating the first history row are dropped from
        the numerator while their calendar days stay in the denominator, and
        the window exceeds the series age outright.
  (ii)  FIT-BOUNDARY ABSORPTION. n_graded counts EVAL-window games only. The
        split is _vintage_cut_index = min(target_idx, half_idx): while the fit
        window holds fewer than VINTAGE_FIT_TARGET_GAMES (300), the
        half-of-dates clamp governs and roughly half of the archive's growth
        is absorbed by the fit window instead of the counter.
  (iii) MISSED NIGHTS. Nights the nightly did not run, or ran against an eval
        artifact that had not refreshed, contribute zero increments inside the
        diffable span.

The product of the three factors must reproduce the measured gap with a
remainder of ~0; a material remainder would mean a fourth mechanism nobody has
named. RUN IT:

    python tools/betting_clock_probe.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"

#: betting_model.py's own measured constant: completed MLB games per calendar
#: date over 130 dates of the 2026 season. The headline "19x" is against this.
SCHEDULE_GAMES_PER_DAY = 13.1


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def probe() -> dict:
    out: dict = {}

    # ------------------------------------------------------------------ 1.
    # The learning series, and the published rate recomputed by hand.
    learn = _load(DATA / "betting_learning.json") or {}
    latest = learn.get("latest") or {}
    hist = learn.get("history") or []
    vclock = ((latest.get("clocks") or {}).get("vintage_sample")) or {}
    pub_rate = (vclock.get("rate") or {})
    latest_date = latest.get("date")
    window = int(pub_rate.get("window_days") or 28)

    # The build differences the history it loaded BEFORE appending today's
    # row, so the replication uses rows strictly before latest.date.
    pts = [(r["date"], r["vintage_n_graded"]) for r in hist
           if r.get("date") and r.get("vintage_n_graded") is not None
           and (not latest_date or r["date"] < latest_date)]
    diffs = {d1: max(0, n1 - n0) for (d0, n0), (d1, n1) in zip(pts, pts[1:])}
    cutoff = pub_rate.get("window_from")
    in_window = sum(n for d, n in diffs.items() if not cutoff or d >= cutoff)
    hand_rate = round(in_window / window, 4) if window else None

    first_row = pts[0] if pts else (None, None)
    last_row = pts[-1] if pts else (None, None)
    span_days = _days(first_row[0], last_row[0]) if len(pts) >= 2 else None
    arrivals_span = sum(diffs.values())

    out["series"] = {
        "history_rows_diffed": len(pts),
        "first_row": {"date": first_row[0], "n_graded": first_row[1]},
        "last_row": {"date": last_row[0], "n_graded": last_row[1]},
        "published_per_day": pub_rate.get("per_day"),
        "recomputed_per_day": hand_rate,
        "replicates": hand_rate == pub_rate.get("per_day"),
        "arrivals_in_window": in_window,
        "diffable_span_days": span_days,
        "artifact_a": (f"{first_row[1]} games were already graded when the "
                       f"series began on {first_row[0]}; every arrival before "
                       f"that row is dropped from the numerator while the "
                       f"{max(0, _days(cutoff, first_row[0])) if cutoff and first_row[0] else '?'} "
                       f"window days from {cutoff} to {first_row[0]} stay in "
                       "the denominator"),
        "artifact_b": (f"the {window}-day window exceeds the series age: the "
                       f"diffable span is {span_days} day(s) "
                       f"({first_row[0]} to {last_row[0]})"),
    }

    # ------------------------------------------------------------------ 2.
    # The eval artifact's vintage split, recomputed from the games cache.
    evald = _load(DATA / "betting_model_eval.json") or {}
    v = evald.get("vintage") or {}
    n_gradable, n_graded = int(v.get("n_gradable") or 0), int(v.get("n_graded") or 0)
    first_g, last_g = v.get("first_graded_date"), v.get("last_graded_date")
    split = v.get("split_date")

    import betting_model as bm
    games = _load(ROOT / ".cache" / "betting" / "completed_games.json") or []
    in_range = [g for g in games
                if first_g and last_g and first_g <= (g.get("date") or "") <= last_g]
    dates = sorted({g["date"] for g in in_range})
    per_date = {}
    for g in in_range:
        per_date[g["date"]] = per_date.get(g["date"], 0) + 1
    # The two candidate cuts, computed separately so the report can say which
    # one governed rather than only what their min was.
    cum, target_idx = 0, len(dates) - 1
    for i, d in enumerate(dates):
        cum += per_date.get(d, 0)
        if cum >= bm.VINTAGE_FIT_TARGET_GAMES:
            target_idx = i + 1
            break
    half_idx = max(1, int(len(dates) * bm.VINTAGE_FIT_MAX_DATE_SHARE))
    cut_idx = bm._vintage_cut_index([{"date": g["date"]} for g in in_range], dates)
    recomputed_split = dates[cut_idx] if dates else None
    fit_n = sum(n for d, n in per_date.items() if d < (recomputed_split or ""))
    eval_n = sum(n for d, n in per_date.items() if d >= (recomputed_split or ""))
    archive_days = (_days(first_g, last_g) + 1) if first_g and last_g else None

    out["vintage_split"] = {
        "n_gradable": n_gradable,
        "n_graded_eval": n_graded,
        "cache_games_in_range": len(in_range),
        "cache_matches_n_gradable": len(in_range) == n_gradable,
        "n_dates": len(dates),
        "archive_calendar_days": archive_days,
        "target_idx": target_idx,
        "half_idx": half_idx,
        "half_clamp_governs": half_idx < target_idx,
        "split_date_artifact": split,
        "split_date_recomputed": recomputed_split,
        "split_replicates": recomputed_split == split,
        "fit_games": fit_n,
        "eval_games": eval_n,
        "eval_matches_n_graded": eval_n == n_graded,
        "fit_target": bm.VINTAGE_FIT_TARGET_GAMES,
        "fit_below_target": fit_n < bm.VINTAGE_FIT_TARGET_GAMES,
        "note": ("while fit_games < VINTAGE_FIT_TARGET_GAMES the half-of-dates "
                 "clamp sets the cut, so the eval counter receives only the "
                 "later half of the dates and its share of every new one"),
    }

    # ------------------------------------------------------------------ 3.
    # The vintage store against the calendar.
    store = ROOT / ".cache" / "leaderboard_vintages"
    have = sorted(p.name[:10] for p in store.glob("*.json")) if store.exists() else []
    missing = []
    if have:
        d0, d1 = date.fromisoformat(have[0]), date.fromisoformat(have[-1])
        allday = {(d0 + timedelta(days=i)).isoformat()
                  for i in range((d1 - d0).days + 1)}
        missing = sorted(allday - set(have))
    out["vintage_store"] = {
        "n_snapshots": len(have),
        "first": have[0] if have else None,
        "last": have[-1] if have else None,
        "n_missing_days": len(missing),
        "missing_days": missing,
    }

    # ------------------------------------------------------------------ 4.
    # Missed nights. job_heartbeat.json only holds LAST runs, so the durable
    # record of a missed night is a gap in the learning history itself plus a
    # zero-increment row where the build ran against a stale eval.
    hb = _load(DATA / "job_heartbeat.json") or {}
    jobs = hb.get("jobs") or {}
    # The gap scan runs over the FULL history span including today's row, so a
    # night missing right at the series edge (2026-08-15 sat between the
    # 08-14 and 08-16 rows) is reported rather than sliced off with the edge.
    all_dates = sorted({r.get("date") for r in hist if r.get("date")})
    series_days = []
    if len(all_dates) >= 2:
        d0, d1 = date.fromisoformat(all_dates[0]), date.fromisoformat(all_dates[-1])
        series_days = [(d0 + timedelta(days=i)).isoformat()
                       for i in range((d1 - d0).days + 1)]
    no_row = [d for d in series_days if d not in set(all_dates)]
    zero_rows = [d for d, n in diffs.items() if n == 0]
    out["missed_nights"] = {
        "dates_with_no_history_row": no_row,
        "zero_increment_rows": zero_rows,
        "heartbeat_last_learning_run": (jobs.get("betting_learning") or {}).get("last_success_at"),
        "heartbeat_last_vintage_run": (jobs.get("leaderboard_vintage") or {}).get("last_success_at"),
        "note": ("a zero-increment row is a night the build ran but the eval "
                 "artifact had not refreshed its graded count; a missing row "
                 "is a night the nightly did not reach betting_learning at all"),
    }

    # ------------------------------------------------------------------ 5.
    # The decomposition.
    r_pub = pub_rate.get("per_day") or 0.0
    r_span = (arrivals_span / span_days) if span_days else None
    r_arch = (n_gradable / archive_days) if archive_days else None
    s_eval = (n_graded / n_gradable) if n_gradable else None

    f_i = (window / span_days) if span_days else None
    f_ii = (1.0 / s_eval) if s_eval else None
    f_iii = ((r_arch * s_eval) / r_span) if (r_arch and s_eval and r_span) else None
    gap_measured = (r_arch / r_pub) if (r_arch and r_pub) else None
    gap_headline = (SCHEDULE_GAMES_PER_DAY / r_pub) if r_pub else None
    product = (f_i * f_ii * f_iii) if all(x for x in (f_i, f_ii, f_iii)) else None
    remainder = (gap_measured / product) if (gap_measured and product) else None

    out["decomposition"] = {
        "published_rate_per_day": r_pub,
        "true_span_rate_per_day": round(r_span, 3) if r_span else None,
        "archive_rate_per_day": round(r_arch, 3) if r_arch else None,
        "eval_share_of_archive": round(s_eval, 4) if s_eval else None,
        "gap_headline_vs_13_1": round(gap_headline, 2) if gap_headline else None,
        "gap_measured_vs_archive": round(gap_measured, 2) if gap_measured else None,
        "factor_i_series_youth_denominator": round(f_i, 2) if f_i else None,
        "factor_ii_fit_boundary_absorption": round(f_ii, 2) if f_ii else None,
        "factor_iii_missed_nights": round(f_iii, 2) if f_iii else None,
        "product_of_factors": round(product, 2) if product else None,
        "unexplained_remainder": (round(remainder - 1.0, 4)
                                  if remainder is not None else None),
        "headline_minus_measured": (round(gap_headline / gap_measured, 3)
                                    if gap_headline and gap_measured else None),
        "reading": ("factor i is pure geometry (window over diffable span); "
                    "factor ii is the eval window's share of the archive under "
                    "the half-date clamp; factor iii is how far the span's "
                    "actual graded arrivals fell below the archive rate times "
                    "that share, which is where the missed and zero-increment "
                    "nights land. The remainder must be ~0; anything left "
                    "beyond it would be a mechanism this probe has not named. "
                    "The headline_minus_measured ratio is the schedule "
                    "constant (13.1 over 130 season dates) against this "
                    "archive window's own density, not a clock defect."),
    }
    return out


def main() -> int:
    print(json.dumps(probe(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
