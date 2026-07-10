# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Re-classify every existing acquisitions row from data — purge the IFA default.

run_monthly used to label any prospect WITHOUT a matched /draft record as
'international_fa', and its draft lookup only spanned a 10-year window — so every
draftee drafted longer ago than that (e.g. Cole Ragans, 2016 R1 #30 TEX, a
graduate frozen outside the window) read as an international free agent. ~54% of
the 'international_fa' cohort carry Jun-Aug (draft-month) signing dates — the
tell of a mis-tagged domestic draftee.

This backfill re-derives each row via acquisition_classify.classify_acquisition:
  * fetch /draft across the full year span the tracked players could have been
    drafted in (per-player career span → union), matched by mlbam_id → 'draft'
    (year / round / overall / team from the authoritative draft record);
  * else assert 'international_fa' only on POSITIVE evidence — an explicit
    ifa_timeseries signing, or the row's stored signing date falling in the
    international window (Jan-Apr);
  * else 'unknown' ("Entry type not on file").

Uses each row's ALREADY-STORED signing_date for the window test, so it makes no
new /transactions calls — only the /draft fetches (cached 30 days). Idempotent.
After running, regenerate the exports (run_monthly.rebuild_only).

Usage:
    python tools/backfill_acquisition_types.py --dry-run   # report only
    python tools/backfill_acquisition_types.py             # apply
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from acquisition_classify import classify_acquisition, load_ifa_signing_ids  # noqa: E402


def _mlbam_by_key() -> dict[str, int]:
    """Union of every player_key → mlbam_id we can resolve: the two export
    sidecars (active + graduates) plus the DB tables that carry the id."""
    out: dict[str, int] = {}

    def _add(key, mid):
        if key and mid is not None and key not in out:
            try:
                out[key] = int(mid)
            except (ValueError, TypeError):
                pass

    for fn in ("timeseries.json", "debuts.json"):
        p = ROOT / "data" / fn
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        players = data.get("players") if isinstance(data, dict) else data
        for pl in (players or []):
            _add(pl.get("player_key"), pl.get("mlbam_id"))

    con = sqlite3.connect(str(ROOT / "prospects.db"))
    for tbl in ("draft_players", "overseas_players", "player_photos", "tjstats_snapshots"):
        try:
            for k, mid in con.execute(
                    f"SELECT player_key, mlbam_id FROM {tbl} WHERE mlbam_id IS NOT NULL"):
                _add(k, mid)
        except sqlite3.Error:
            pass
    con.close()
    return out


def main(dry_run: bool = False) -> None:
    from stats import bulk_fetch_drafts
    from storage import load_acquisitions, upsert_acquisitions

    acq = load_acquisitions()
    print(f"acquisitions on file: {len(acq)}")
    print("  before:", dict(Counter(r.get("method") for r in acq.values())))

    mlbam = _mlbam_by_key()
    print(f"resolved mlbam_id for {len(set(acq) & set(mlbam))}/{len(acq)} rows")

    # Per-player career span → the union of years the tracked players could
    # plausibly have been drafted in. The stored signing/draft year is the best
    # proxy; floor a couple years below the earliest so a player who debuted the
    # year after their draft is still covered.
    years = [r["year"] for r in acq.values() if r.get("year")]
    lo = (min(years) - 1) if years else (date.today().year - 12)
    hi = date.today().year
    print(f"fetching /draft for {lo}-{hi} ({hi - lo + 1} years, cached)")
    draft_by_id = bulk_fetch_drafts(range(lo, hi + 1))
    print(f"  indexed {len(draft_by_id)} draft picks by mlbam_id")

    ifa_mids, ifa_keys = load_ifa_signing_ids(ROOT / "data" / "ifa_timeseries.json")
    print(f"explicit ifa_timeseries signings: {len(ifa_keys)} keys / {len(ifa_mids)} ids")

    updated: dict[str, dict] = {}
    transitions: Counter = Counter()
    skipped_no_id = 0
    for key, old in acq.items():
        # Trust an existing confirmed DRAFT record — it was set from a matched
        # draft pick; never downgrade it (the bug is the opposite direction).
        if old.get("method") == "draft":
            continue
        mid = mlbam.get(key)
        if mid is None:
            # Can't verify against /draft without an id — leave the row as-is
            # rather than guess (guardrail: don't regress / don't fabricate).
            skipped_no_id += 1
            continue
        pick = draft_by_id.get(mid)
        # The original SFA/SGN signing context is already stored on IFA/unknown
        # rows — reuse it (no new /transactions calls).
        signing = {
            "year":         old.get("year"),
            "team_name":    old.get("team_name"),
            "signing_date": old.get("signing_date"),
        }
        ifa_match = (key in ifa_keys) or (mid is not None and mid in ifa_mids)
        new = classify_acquisition(pick, signing, ifa_match)
        # Preserve a known signing bonus the draft/IFA scrapers layered in
        # (Spotrac) when the fresh record doesn't carry one.
        if new.get("bonus_usd") is None and old.get("bonus_usd") is not None:
            new["bonus_usd"] = old["bonus_usd"]
        if new["method"] != old.get("method"):
            transitions[f"{old.get('method')} -> {new['method']}"] += 1
        # Upsert when anything material changed.
        if any(new.get(f) != old.get(f) for f in
               ("method", "year", "round_label", "pick_round", "pick_overall",
                "team_name", "school")):
            new["player_key"] = key
            updated[key] = new

    print("  transitions:", dict(transitions))
    print(f"  rows to update: {len(updated)} | left as-is (no id / trusted draft): "
          f"{skipped_no_id} no-id + {sum(1 for r in acq.values() if r.get('method')=='draft')} draft")
    print("  after:", dict(Counter((updated.get(k) or acq[k]).get("method") for k in acq)))

    # Spot-check Ragans.
    rg = (updated.get("cole_ragans") or acq.get("cole_ragans") or {})
    print(f"  Cole Ragans -> method={rg.get('method')} year={rg.get('year')} "
          f"round={rg.get('round_label')} overall={rg.get('pick_overall')} team={rg.get('team_name')}")

    if dry_run:
        print("DRY RUN — no writes.")
        return
    n = upsert_acquisitions(updated) if updated else 0
    print(f"upserted {n} corrected acquisitions. Re-run run_monthly.rebuild_only to re-export.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
