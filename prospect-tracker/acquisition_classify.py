# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Derive a player's ORIGINAL acquisition type from data — never a default.

Replaces the old run_monthly rule that labeled every prospect WITHOUT a matched
draft record as 'international_fa' (the convention "treat undrafted prospects as
IFA"). That fabricated a category for ~half the IFA cohort: any draftee whose
/draft year fell outside the lookback window (e.g. Cole Ragans, 2016 R1 #30 TEX)
read as an international free agent.

Per the data-correctness guardrail:
  * DRAFT is asserted only from an explicit /draft record (matched by mlbam_id),
    fetched across the player's full career span so older picks resolve too.
  * INTERNATIONAL FA is asserted when the player is NOT in the (comprehensive)
    draft data but DOES have a free-agent signing on file — the signing
    transaction is the positive evidence that they entered as a free agent, and
    the absence of a draft pick reliably means they didn't go through the draft.
  * Anything with neither a draft record nor any signing context is 'unknown'
    ("Entry type not on file"), surfacing the gap instead of guessing.

The amateur draft (June) and the international amateur window overlap on the
calendar — and the int'l window opened JULY 2 pre-2021 (Jan 15 from 2021 on) — so
a signing MONTH can't separate the two (an early validation that gated IFA on a
Jan-Apr window mislabeled ~382 genuine pre-2021 July-2 signees as 'unknown').
The draft record is the real discriminator: a free-agent signing with no pick in
the comprehensive draft set is an international / free-agent entry.
"""

from __future__ import annotations

import json
from pathlib import Path


def _blank(method: str) -> dict:
    return {
        "method":       method,
        "year":         None,
        "round_label":  None,
        "pick_round":   None,
        "pick_overall": None,
        "bonus_usd":    None,
        "team_name":    None,
        "school":       None,
        "signing_date": None,
    }


def classify_acquisition(draft_pick: dict | None,
                         signing: dict | None,
                         ifa_match: bool) -> dict:
    """Return an `acquisitions` record derived from data. NEVER defaults to IFA.

    Args:
      draft_pick: the {year, round_label, pick_round, pick_overall, bonus_usd,
                  team_name, school} for this player's mlbam_id from /draft, or
                  None when no draft record was found.
      signing:    the {year, team_name, signing_date} of the original SFA/SGN
                  signing transaction, or None.
      ifa_match:  True when the player appears in the explicit ifa_timeseries
                  signings (the authoritative international-amateur source).

    Precedence:
      1. explicit DRAFT record                         → 'draft'
      2. no draft + a signing on file (or ifa_match)   → 'international_fa'
      3. no draft + no signing context                 → 'unknown'  (not on file)

    Any signing context we *do* have (date / team / year) is retained for display
    even in the 'unknown' case — without asserting a category.
    """
    if draft_pick is not None:
        rec = _blank("draft")
        rec.update({
            "year":         draft_pick.get("year"),
            "round_label":  draft_pick.get("round_label"),
            "pick_round":   draft_pick.get("pick_round"),
            "pick_overall": draft_pick.get("pick_overall"),
            "bonus_usd":    draft_pick.get("bonus_usd"),
            "team_name":    draft_pick.get("team_name"),
            "school":       draft_pick.get("school"),
            "signing_date": draft_pick.get("signing_date"),
        })
        return rec

    # No draft record. With comprehensive /draft coverage (the full career-span
    # window) the ABSENCE of a pick reliably means the player did not go through
    # the amateur draft, so a free-agent signing on file is an international /
    # free-agent signing — the signing transaction itself is the positive
    # evidence (ifa_match is explicit confirmation). NOTE the international
    # amateur window was July 2 pre-2021 (Jan 15 from 2021 on), so IFA signings
    # legitimately span the calendar — there is no reliable month gate; the draft
    # record is the discriminator. Only a TOTAL absence of signing context (no
    # date / team / year) stays 'unknown'.
    sig = signing or {}
    has_signing = bool(sig.get("signing_date") or sig.get("team_name") or sig.get("year"))
    rec = _blank("international_fa" if (ifa_match or has_signing) else "unknown")
    rec.update({
        "year":         sig.get("year"),
        "team_name":    sig.get("team_name"),
        "signing_date": sig.get("signing_date"),
    })
    return rec


def load_ifa_signing_ids(ifa_timeseries_path) -> tuple[set[int], set[str]]:
    """(mlbam_ids, player_keys) for every explicit ifa_timeseries signing across
    all tracked classes — the positive international-amateur evidence set."""
    mids: set[int] = set()
    keys: set[str] = set()
    try:
        data = json.loads(Path(ifa_timeseries_path).read_text(encoding="utf-8"))
    except Exception:
        return mids, keys
    for cls in (data.get("classes") or []):
        for sg in (cls.get("signings") or []):
            mid = sg.get("mlbam_id")
            if mid is not None:
                try:
                    mids.add(int(mid))
                except (ValueError, TypeError):
                    pass
            k = sg.get("player_key")
            if k:
                keys.add(k)
    return mids, keys
